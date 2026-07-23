from __future__ import annotations

import json
import math
from typing import Any

from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.boundary_models import validate_vfx_manifest_boundary

from infini_local.core.effect_catalog import normalize_attack_pattern
from infini_local.core.llm_stage_messages import agent_handoff, stage_chat_message
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
from infini_local.core.vfx_runtime_slots import (
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

VFX_FALLBACK_POLICY = "llm_vfx_then_explicit_direct_else_inert"


def _log_vfx_fallback_policy(
    data: dict[str, Any],
    recipe_key_value: str,
    *,
    history_state: str,
    request_mode: str,
    failure_phase: str,
    reason: str,
) -> None:
    """Emit one warning before explicit direct VFX or an inert manifest takes over."""
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
        "fallbackTarget": "explicit_runtime_vfx_or_empty_manifest",
    })


_VFX_PROJECTILE_EVENTS = frozenset({"travel", "active", "tick", "hit", "kill", "expire"})


def _vfx_executable_events(data: dict[str, Any]) -> set[str]:
    gameplay_raw = data.get("gameplay")
    gameplay: dict[str, Any] = gameplay_raw if isinstance(gameplay_raw, dict) else {}
    attack_raw = data.get("attack")
    attack: dict[str, Any] = attack_raw if isinstance(attack_raw, dict) else {}
    result_kind = str(gameplay.get("kind") or data.get("category") or "").strip().lower()
    if result_kind in {"armor", "accessory"}:
        allowed = {"while_equipped"}
    else:
        allowed = {"while_held", "on_use"}
        alt_use_mode = str(gameplay.get("altUseMode") or "").strip().lower()
        if alt_use_mode not in {"", "none"}:
            allowed.add("on_alt_use")

    runtime_family = str(attack.get("runtimeFamily") or "").strip().lower()
    if bool(attack.get("enabled")) and runtime_family not in {"none", "swing"}:
        allowed.update(_VFX_PROJECTILE_EVENTS)
    return allowed


def _vfx_director_runtime_event_errors(raw: Any, data: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("slots"), list):
        return []
    allowed = sorted(_vfx_executable_events(data))
    errors: list[dict[str, Any]] = []
    for index, slot in enumerate(raw["slots"]):
        if not isinstance(slot, dict):
            continue
        event = str(slot.get("event") or "").strip()
        if event and event not in allowed:
            errors.append({
                "path": f"slots[{index}].event",
                "error": "event_not_executable",
                "actual": event,
                "allowed": allowed,
            })
    return errors


def _vfx_director_item_validation_report(raw: Any, data: dict[str, Any]) -> dict[str, Any]:
    report = _vfx_director_validation_report(raw)
    runtime_errors = _vfx_director_runtime_event_errors(raw, data)
    if runtime_errors:
        report["errors"] = [*report.get("errors", []), *runtime_errors]
        report["valid"] = False
    return report


def _vfx_validate_director_output(raw: dict[str, Any], data: dict[str, Any], recipe_key_value: str, parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None) -> dict[str, Any] | None:
    report = _vfx_director_item_validation_report(raw, data)
    if not report.get("valid"):
        return None
    if not isinstance(raw, dict):
        return None
    surface = vfx_director_surface()
    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list):
        return None
    max_slots = max(2, min(8, VFX_LLM_DIRECTOR_MAX_SLOTS))
    raw_slots = [s for s in raw_slots if isinstance(s, dict)][:max_slots]

    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    pattern = normalize_attack_pattern(
        attack.get("pattern") or attack.get("attackPattern") or "basic"
    ) or "basic"
    gameplay: dict[str, Any] = {}
    gameplay_value = data.get("gameplay")
    if isinstance(gameplay_value, dict):
        gameplay = gameplay_value
    power = float(attack.get("powerBudget") or gameplay.get("powerBudget") or 1.0)
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
        start_tick = _vfx_director_number_required(
            slot, "startTick", 0, 120, integer=True
        ) if "startTick" in slot else 0
        repeat_every = _vfx_director_number_required(
            slot, "repeatEvery", 0, 120, integer=True
        ) if "repeatEvery" in slot else 0
        if any(x is None for x in [scale, density, duration, alpha, spread, jitter, budget_weight, signature_weight, visual_cost, fade_in, fade_out, phase_offset, start_tick, repeat_every]):
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
            "startTick": start_tick,
            "repeatEvery": repeat_every,
            "source": "llmDirector",
        })

    slots = [_vfx_compile_slot(slot, seed, i, power, effect_magnitude) for i, slot in enumerate(compiled_raw)]
    slots = _vfx_arbitrate_slots(slots, budget_class)
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
            "selectedReasons": ["llm_director_validated"],
            "topCandidates": [],
            "wordProbe": [],
        }
    }
    return manifest


def try_llm_vfx_director(parent_a: dict[str, Any] | None, parent_b: dict[str, Any] | None, child_item: dict[str, Any], recipe_key_value: str, llm_client: Any = None) -> dict[str, Any] | None:
    """Optional Gemma E4B VFX Director pass.

    Product policy: VFX is optional presentation, not the main authored gameplay feature.
    One self-contained accepted-product dossier is sent to the Director. ``VFX repair``
    appends the invalid Director artifact plus exact validator feedback and asks for a
    corrected manifest; there is no second standalone author path.

    If the bounded repair fails, keep the valid item and use only an explicit compiled
    visual cue; absent that authority, the manifest is inert. The exact failure
    phase/reason is emitted to events.ndjson.
    """
    if not VFX_LLM_DIRECTOR_ENABLED or llm_client is None:
        return None
    constraints = {
        "attackPattern": (child_item.get("attack") or {}).get("pattern") if isinstance(child_item.get("attack"), dict) else "basic",
        "allowedEvents": sorted(_vfx_executable_events(child_item)),
        "noBakedCommands": True,
        "slots": [0, max(2, VFX_LLM_DIRECTOR_MAX_SLOTS)],
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
                return "vfxLlmDirectorStageFallbackReason"
            return "vfxLlmDirectorUnknownModeFallbackReason"

        def _set_mode_fallback(reason: str) -> None:
            debug[_reason_key()] = reason
            debug["vfxLlmDirectorLastFallbackReason"] = reason

        report = _vfx_director_item_validation_report(raw, child_item)
        debug["vfxLlmDirectorValidationErrorCount"] = len(report.get("errors", []))
        debug["vfxLlmDirectorValidationFields"] = _vfx_director_error_fields(report)
        repair_budget = min(1, max(0, VFX_LLM_DIRECTOR_REPAIR_ATTEMPTS))
        debug["vfxLlmDirectorRepairAttempts"] = 0
        debug["vfxLlmDirectorRepairEnabled"] = repair_budget
        if report.get("valid"):
            manifest = _vfx_validate_director_output(raw, child_item, recipe_key_value, parent_a, parent_b)
            if isinstance(manifest, dict):
                comp = manifest.setdefault("debug", {}).setdefault("composition", {})
                comp["repairAttempted"] = False
                comp["validationErrorCountBeforeRepair"] = 0
                comp["vfxPath"] = "llm_director"
                return manifest
            _set_mode_fallback("valid_contract_but_compile_failed")
            return None

        if repair_budget <= 0:
            _set_mode_fallback("invalid_director_output_repair_disabled")
            debug["vfxLlmDirectorValidationReport"] = bounded_json_dumps(report, max_chars=6000)
            return None

        repair_raw: Any = raw
        last_report = report
        for attempt in range(1, repair_budget + 1):
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
            last_report = _vfx_director_item_validation_report(repair_raw, child_item)
            debug["vfxLlmDirectorRepairLastErrorCount"] = len(last_report.get("errors", []))
            debug["vfxLlmDirectorRepairLastFields"] = _vfx_director_error_fields(last_report)
            if last_report.get("valid"):
                manifest = _vfx_validate_director_output(repair_raw, child_item, recipe_key_value, parent_a, parent_b)
                if isinstance(manifest, dict):
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
        messages = build_vfx_director_handoff_messages(
            child_item, parent_a, parent_b, surface, constraints
        )
        if not messages:
            raise ValueError("self-contained VFX dossier was not built")
        raw = llm_client(
            system, {}, VFX_LLM_DIRECTOR_MAX_TOKENS, VFX_LLM_DIRECTOR_TEMPERATURE,
            VFX_LLM_DIRECTOR_TIMEOUT, messages=messages,
        )
        manifest = validate_or_repair(
            raw, "authoritative_stage_dossier_v31", base_messages=messages
        )
        if isinstance(manifest, dict):
            debug["vfxLlmDirectorMode"] = "authoritative_stage_dossier_v31"
            debug["vfxLlmDirectorMessages"] = len(messages)
            debug["vfxPath"] = "llm_director" if manifest.get("slots") else "llm_director_empty"
            return manifest
        final_reason = (
            debug.get("vfxLlmDirectorStageFallbackReason")
            or "invalid_director_output"
        )
        debug["vfxLlmDirectorFinalFallbackReason"] = final_reason
        debug["vfxLlmDirectorFallbackReason"] = final_reason
        debug["vfxPath"] = "vfx_director_rejected"
        repair_attempts = int(debug.get("vfxLlmDirectorRepairAttempts") or 0)
        failure_phase = (
            "repair_exhausted"
            if repair_attempts > 0
            else ("compile_failed" if "compile_failed" in str(final_reason) else "initial_validation")
        )
        _log_vfx_fallback_policy(
            child_item,
            recipe_key_value,
            history_state="self_contained",
            request_mode="authoritative_stage_dossier_v31",
            failure_phase=failure_phase,
            reason=str(final_reason),
        )
        return None
    except Exception as e:
        debug["vfxLlmDirectorError"] = repr(e)
        debug["vfxLlmDirectorFinalFallbackReason"] = "exception"
        debug["vfxLlmDirectorFallbackReason"] = "exception"
        debug["vfxPath"] = "vfx_director_rejected"
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
    attack_value = data.get("attack")
    attack: dict[str, Any] = attack_value if isinstance(attack_value, dict) else {}
    director_manifest = try_llm_vfx_director(parent_a, parent_b, data, recipe_key_value, llm_director)
    if isinstance(director_manifest, dict):
        wire_manifest = validate_vfx_manifest_boundary(director_manifest)
        data["vfxManifest"] = director_manifest
        attack["vfxManifestJson"] = json.dumps(wire_manifest, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        data.setdefault("debug", {})["vfxManifest"] = bounded_json_dumps(director_manifest, max_chars=12000)
        data.setdefault("debug", {})["vfxLlmDirector"] = "used"
        data.setdefault("debug", {})["vfxPath"] = (
            "llm_director" if director_manifest.get("slots") else "llm_director_empty"
        )
        return data
    direct_manifest = _vfx_runtime_plan_direct_manifest(data, recipe_key_value, reroll_salt)
    if isinstance(direct_manifest, dict):
        wire_manifest = validate_vfx_manifest_boundary(direct_manifest)
        data["vfxManifest"] = direct_manifest
        attack["vfxManifestJson"] = json.dumps(wire_manifest, ensure_ascii=False, separators=(",", ":"))
        data["attack"] = attack
        data.setdefault("debug", {})["vfxManifest"] = bounded_json_dumps(direct_manifest, max_chars=12000)
        data.setdefault("debug", {})["vfxPath"] = "runtime_plan_direct_empty" if not direct_manifest.get("slots") else "runtime_plan_direct"
        return data
    empty_manifest = validate_vfx_manifest_boundary({
        "effectMagnitude": 0.0,
        "visualBudgetClass": "tiny",
        "budget": {
            "effectMagnitude": 0.0,
            "visualBudgetClass": "tiny",
            "maxParticlesPerTick": 0,
            "maxParticlesTotal": 0,
            "maxDrawCalls": 0,
            "spawnRateMultiplier": 0.0,
            "enableSoftGlow": False,
            "enablePointSparks": False,
            "enablePersistentSmoke": False,
            "emergencyCap": True,
        },
        "slots": [],
    })
    data["vfxManifest"] = empty_manifest
    attack["vfxManifestJson"] = json.dumps(
        empty_manifest, ensure_ascii=False, separators=(",", ":")
    )
    data["attack"] = attack
    debug = data.setdefault("debug", {})
    debug["vfxPath"] = "empty_no_authored_vfx"
    debug["vfxManifest"] = bounded_json_dumps(empty_manifest, max_chars=12000)
    return data


# Debug endpoints only. Production attach_hybrid_vfx_manifest never calls these helpers.
def _vfx_find_recipe(recipe_id: str) -> dict[str, Any] | None:
    rid = str(recipe_id or "").strip()
    if not rid:
        return None
    for recipe in get_vfx_recipes():
        if str(recipe.get("id") or "") == rid:
            return recipe
    return None


def _vfx_manifest_from_recipe(
    data: dict[str, Any],
    recipe: dict[str, Any],
    recipe_key_value: str,
    reroll_salt: Any = "",
    forced: bool = False,
) -> dict[str, Any]:
    """Compile an explicitly requested recipe for the isolated debug API only."""
    attack = data.setdefault("attack", {}) if isinstance(data.get("attack"), dict) else data.setdefault("attack", {})
    pattern = normalize_attack_pattern(
        attack.get("pattern") or attack.get("attackPattern") or attack.get("Pattern") or "basic"
    )
    selector_key = f"{recipe_key_value}|vfxsalt={str(reroll_salt or data.get('recipeMeta', {}).get('vfxRerollSalt', '') or '')}"
    power = (
        float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0)
        if isinstance(data.get("gameplay"), dict)
        else float(attack.get("powerBudget") or 1.0)
    )
    seed = _vfx_seed_int(selector_key, recipe.get("id"), data.get("id"), pattern)
    budget = _vfx_budget_for_recipe(recipe, power, seed, data)
    effect_magnitude = float(budget.get("effectMagnitude") or 0.5)
    slots = [
        _vfx_compile_slot(slot, seed, i, power, effect_magnitude)
        for i, slot in enumerate(recipe.get("slots") or [])
        if isinstance(slot, dict)
    ]
    slots = _vfx_arbitrate_slots(
        slots, str(budget.get("visualBudgetClass") or "normal")
    )
    manifest = validate_vfx_manifest_boundary({
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
                "mode": "debug_forced_recipe" if forced else "debug_direct_recipe",
                "baseRecipeId": str(recipe.get("id") or "unknown"),
                "preArbitrationSlotCount": len(recipe.get("slots") or []),
                "postArbitrationSlotCount": len(slots),
                "blendedSlots": [],
                "proceduralSlots": [],
            },
            "pattern": pattern,
            "roles": sorted(_vfx_available_roles(data)),
            "selectedScore": 999.0 if forced else 0.0,
            "selectedReasons": ["explicit_debug_recipe"],
            "topCandidates": [],
            "wordProbe": [],
        },
    })
    data["vfxManifest"] = manifest
    attack["vfxManifestJson"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":")
    )
    data["attack"] = attack
    data.setdefault("debug", {})["vfxManifest"] = bounded_json_dumps(
        manifest, max_chars=12000
    )
    return data


def compact_vfx_recipe_card(recipe: dict[str, Any]) -> dict[str, Any]:
    slots_value = recipe.get("slots")
    slots: list[Any] = slots_value if isinstance(slots_value, list) else []
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
        "backends": sorted({
            str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("rendererKind")))
            for x in slots if isinstance(x, dict)
        }),
        "stages": sorted({
            str(x.get("stage") or _vfx_event_stage(x.get("event"), x.get("rendererKind")))
            for x in slots if isinstance(x, dict)
        }),
        "bakedEligibleSlots": sum(
            1 for x in slots
            if isinstance(x, dict) and _vfx_should_bake_slot(
                x,
                str(x.get("event") or ""),
                str(x.get("rendererKind") or ""),
                str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("rendererKind"))),
            )
        ),
        "expandedFromMacros": bool(recipe.get("expandedFromMacros")),
        "useMacros": recipe.get("useMacros", []),
        "macroIds": sorted({
            str(x.get("macroId"))
            for x in slots if isinstance(x, dict) and x.get("macroId")
        }),
    }


__all__ = [
    "_vfx_validate_director_output",
    "try_llm_vfx_director",
    "attach_hybrid_vfx_manifest",
    "_vfx_find_recipe",
    "_vfx_manifest_from_recipe",
    "compact_vfx_recipe_card",
]
