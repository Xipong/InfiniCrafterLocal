"""Finite VFX stage lifecycle: one Director and at most one conditional Repair."""
from __future__ import annotations

import copy
import json
from typing import Any, Callable, Mapping

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_stage_messages import stage_chat_message
from infini_local.core.vfx import config
from infini_local.core.vfx.projection import (
    _compile_manifest,
    _development_manifest,
    _hydrate_vfx_asset_prompts,
    _sound_projection_receipts,
    audit_vfx_sound_projection,
)
from infini_local.core.vfx.repair import (
    _apply_vfx_repair_patch,
    _build_vfx_repair_scope,
)
from infini_local.core.vfx.surface import _allowed_pairs
from infini_local.core.vfx.validation import validate_vfx_director_output
from infini_local.pipelines.vfx.prompt import (
    _director_system,
    _prompt_packet,
    build_vfx_repair_packet,
)


def _stage_accounting(data: dict[str, Any]) -> dict[str, int]:
    debug = data.setdefault("debug", {})
    accounting = debug.setdefault("llmStageAccounting", {})
    for key in (
        "gameplayAuthorCalls", "gameplayRepairCalls", "visualDirectorCalls",
        "visualRepairCalls", "vfxDirectorCalls", "vfxRepairCalls",
    ):
        accounting.setdefault(key, 0)
    return accounting


def _request(
    llm_director: Callable[..., Any],
    packet: dict[str, Any],
    *,
    repair_errors: list[dict[str, Any]] | None = None,
    previous: Any = None,
    repair_scope: Mapping[str, Any] | None = None,
) -> Any:
    messages = None
    if repair_errors is not None:
        user = build_vfx_repair_packet(packet, previous, repair_scope or {}, repair_errors)
        messages = [
            stage_chat_message("system", "vfx_repair_contract", _director_system(repair=True)),
            stage_chat_message("user", "vfx_repair_context", json.dumps(user, ensure_ascii=False, separators=(",", ":"))),
        ]
        return llm_director(
            _director_system(repair=True), user, int(config.VFX_LLM_DIRECTOR_MAX_TOKENS),
            float(config.VFX_LLM_REPAIR_TEMPERATURE), int(config.VFX_LLM_DIRECTOR_TIMEOUT), messages=messages,
        )
    user = copy.deepcopy(packet)
    return llm_director(
        _director_system(repair=False), user, int(config.VFX_LLM_DIRECTOR_MAX_TOKENS),
        float(config.VFX_LLM_DIRECTOR_TEMPERATURE), int(config.VFX_LLM_DIRECTOR_TIMEOUT), messages=messages,
    )


def attach_vfx_manifest(
    data: dict[str, Any],
    recipe_key_value: str,
    parent_a: dict[str, Any] | None = None,
    parent_b: dict[str, Any] | None = None,
    llm_director: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run one VFX Director call and at most one conditional VFX Repair."""
    if llm_director is None:
        data["vfxManifest"] = _development_manifest(data, recipe_key_value)
        data.setdefault("debug", {})["vfxDirectorStatus"] = "development_inert_manifest"
        return data

    packet = _prompt_packet(data, parent_a, parent_b)
    accounting = _stage_accounting(data)
    accounting["vfxDirectorCalls"] += 1
    raw = _request(llm_director, packet)
    report = validate_vfx_director_output(raw, data)
    if not report["ok"]:
        accounting["vfxRepairCalls"] += 1
        repair_scope = _build_vfx_repair_scope(raw, report["errors"])
        patch = _request(llm_director, packet, repair_errors=report["errors"], previous=raw, repair_scope=repair_scope)
        repaired, repair_audit = _apply_vfx_repair_patch(data, raw, patch or {}, repair_scope, return_audit=True)
        report = validate_vfx_director_output(repaired, data)
        if not report["ok"]:
            raise PlannerUnavailable("VFX Repair did not produce an exact entity/event manifest: " + json.dumps(report["errors"][:16], ensure_ascii=False))
        raw = repaired
        data.setdefault("debug", {})["vfxRepairRawPatch"] = copy.deepcopy(patch)
        data["debug"]["vfxRepairPatch"] = copy.deepcopy(repair_audit.get("filteredPatch") or {})
        data["debug"]["vfxRepairFilterAudit"] = copy.deepcopy(repair_audit)
        data["debug"]["vfxRepairScope"] = copy.deepcopy(repair_scope)
    _hydrate_vfx_asset_prompts(data, report["normalized"])
    manifest = _compile_manifest(data, report["normalized"], recipe_key_value)
    sound_receipts = _sound_projection_receipts(report["normalized"])
    sound_audit = audit_vfx_sound_projection(report["normalized"], manifest, sound_receipts)
    if not sound_audit["ok"]:
        raise PlannerUnavailable("VFX sound projection lost an authored choice: " + json.dumps(sound_audit["errors"], ensure_ascii=False))
    data["vfxManifest"] = manifest
    debug = data.setdefault("debug", {})
    if sound_receipts:
        debug["vfxSoundReceipts"] = sound_receipts
        debug["vfxSoundProjectionAudit"] = sound_audit
    debug["vfxDirectorStatus"] = "validated_and_compiled"
    debug["vfxDirectorRaw"] = copy.deepcopy(raw)
    debug["vfxRuntimePairs"] = _allowed_pairs(data)
    return data
