from __future__ import annotations

"""Author -> low-level runtime -> Visual -> VFX combine pipeline.

This module deliberately contains no weapon classifier, family route, semantic
lowerer, or compatibility path. Gameplay Author owns the complete bounded
runtime program. Deterministic stages only validate, compile, generate assets,
and commit a world-scoped recipe.
"""

import copy
import json
import time
from typing import Any, Callable, Mapping

from infini_local.core import dev_fallback
from infini_local.core.config_bootstrap import (
    APP_VERSION,
    ASSET_PUBLIC_BASE_URL,
    RECIPE_IDENTITY_VERSION,
)
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_config import ALLOW_DETERMINISTIC_DEV_FALLBACK, USE_LLM
from infini_local.core.runtime_authoring import (
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_WIRE_SCHEMA,
    runtime_event_inventory,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.vfx_manifest import VFX_MANIFEST_SCHEMA, attach_hybrid_vfx_manifest
from infini_local.pipelines import generation_debug
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_runtime_program
from infini_local.pipelines.combine_validation import strict_validate_authored_item
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.generated_parent_summary import attach_generated_parent_summary
from infini_local.pipelines.item_power_knowledge import apply_item_knowledge, canonicalize
from infini_local.pipelines.llm_authoring_pipeline import (
    call_llm_vfx_director,
    repair_author_item_after_failure,
    try_llm_plan,
    validate_final_runtime_promise_boundary,
)
from infini_local.pipelines.llm_transport import begin_llm_item_lease, end_llm_item_lease
from infini_local.pipelines.pipeline_visual_config import VISUAL_PIPELINE_PROFILE, contract_versions_payload
from infini_local.pipelines.result_knowledge_card import attach_result_knowledge_card
from infini_local.pipelines.visual_asset_plan import finalize_visual_asset_runtime_gates
from infini_local.pipelines.visual_delivery_gate import assert_visual_delivery_ready, visual_delivery_report
from infini_local.pipelines.visual_generation_pipeline import apply_visual_director, attach_visual
from infini_local.pipelines.visual_sprite_generation import maybe_generate_visual_assets
from infini_local.services import asset_sync_service
from infini_local.storage import world_storage
from infini_local.storage.trace_runtime import trace_event
from infini_local.storage.world_recipe_runtime import (
    cache_get,
    cache_put,
    is_deliverable_recipe_payload,
    normalize_world_id_from_payload,
    quarantine_world_recipe_cache,
    recipe_key,
    sanitize_recipe_for_delivery,
    world_recipe_dir,
)


_STAGE_KEYS = (
    "gameplayAuthorCalls",
    "gameplayRepairCalls",
    "visualDirectorCalls",
    "visualRepairCalls",
    "vfxDirectorCalls",
    "vfxRepairCalls",
)


def _stage_accounting(data: Mapping[str, Any]) -> dict[str, int]:
    debug = data.get("debug") if isinstance(data.get("debug"), Mapping) else {}
    raw = debug.get("llmStageAccounting") if isinstance(debug, Mapping) else {}
    source = raw if isinstance(raw, Mapping) else {}
    return {key: int(source.get(key) or 0) for key in _STAGE_KEYS}


def _assert_stage_topology(data: dict[str, Any]) -> dict[str, Any]:
    """Prove the three-stage topology without manufacturing missing calls."""
    accounting = _stage_accounting(data)
    planner = str((data.get("debug") or {}).get("planner") or "") if isinstance(data.get("debug"), dict) else ""
    if planner.startswith("llm_"):
        expected_baseline = {
            "gameplayAuthorCalls": 1,
            "visualDirectorCalls": 1,
            "vfxDirectorCalls": 1,
        }
        mismatches = [f"{key}={accounting[key]} (expected {value})" for key, value in expected_baseline.items() if accounting[key] != value]
        repair_overruns = [f"{key}={accounting[key]}" for key in ("gameplayRepairCalls", "visualRepairCalls", "vfxRepairCalls") if accounting[key] not in {0, 1}]
        if mismatches or repair_overruns:
            raise PlannerUnavailable("invalid LLM stage topology: " + "; ".join(mismatches + repair_overruns))
    data["llmStageAccounting"] = accounting
    return data


def _vfx_manifest_report(data: Mapping[str, Any]) -> dict[str, Any]:
    manifest = data.get("vfxManifest")
    errors: list[dict[str, str]] = []
    if not isinstance(manifest, Mapping):
        return {"schema": "infini.vfx-wire-report.v1", "ok": False, "errors": [{"path": "$.vfxManifest", "message": "missing VFX manifest"}]}
    if str(manifest.get("schema") or "") != VFX_MANIFEST_SCHEMA:
        errors.append({"path": "$.vfxManifest.schema", "message": f"expected {VFX_MANIFEST_SCHEMA}"})
    allowed = {(str(row.get("entityId") or ""), str(row.get("event") or "")) for row in runtime_event_inventory(data) if isinstance(row, Mapping)}
    seen_ids: set[str] = set()
    slots = manifest.get("slots")
    if not isinstance(slots, list):
        errors.append({"path": "$.vfxManifest.slots", "message": "must be an array"})
        slots = []
    for index, slot in enumerate(slots):
        path = f"$.vfxManifest.slots[{index}]"
        if not isinstance(slot, Mapping):
            errors.append({"path": path, "message": "must be an object"})
            continue
        slot_id = str(slot.get("id") or "")
        pair = (str(slot.get("entityId") or ""), str(slot.get("event") or ""))
        if not slot_id:
            errors.append({"path": path + ".id", "message": "required"})
        elif slot_id in seen_ids:
            errors.append({"path": path + ".id", "message": "duplicate slot id"})
        seen_ids.add(slot_id)
        if pair not in allowed:
            errors.append({"path": path, "message": f"entity/event pair {pair!r} is not present in runtimeProgram"})
    return {"schema": "infini.vfx-wire-report.v1", "ok": not errors, "errors": errors}


def _cached_payload_report(data: Any) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not is_deliverable_recipe_payload(data):
        errors.append({"path": "$", "message": "payload is not deliverable"})
        return {"ok": False, "errors": errors}
    assert isinstance(data, dict)
    if str(data.get("runtimeApiVersion") or "") != RUNTIME_PROGRAM_API_VERSION:
        errors.append({"path": "$.runtimeApiVersion", "message": f"expected {RUNTIME_PROGRAM_API_VERSION}"})
    runtime = data.get("runtimeProgram")
    if not isinstance(runtime, Mapping) or str(runtime.get("schema") or "") != RUNTIME_WIRE_SCHEMA:
        errors.append({"path": "$.runtimeProgram.schema", "message": f"expected {RUNTIME_WIRE_SCHEMA}"})
    wire = validate_runtime_wire(data)
    errors.extend(copy.deepcopy(wire.get("errors") or []))
    visual = visual_delivery_report(data, check_backend_config=False)
    for problem in visual.get("problems") or []:
        errors.append({"path": "$.visual", "message": str(problem)})
    vfx = _vfx_manifest_report(data)
    errors.extend(copy.deepcopy(vfx.get("errors") or []))
    return {"ok": not errors, "errors": errors, "runtime": wire, "visual": visual, "vfx": vfx}


def _quarantine_cached_recipe(*, world_id: str, recipe_key_value: str, reason: str, details: dict[str, Any] | None = None) -> None:
    try:
        path = quarantine_world_recipe_cache(recipe_key_value, world_id, reason, details=details)
        if path:
            trace_event("warn", "COMBINE:cache", "invalid low-level runtime recipe quarantined", {"recipeKey": recipe_key_value, "worldId": world_id, "reason": reason, "path": path})
    except (OSError, ValueError, TypeError) as exc:
        trace_event("warn", "COMBINE:cache", "could not quarantine invalid recipe", {"recipeKey": recipe_key_value, "worldId": world_id, "reason": reason, "error": repr(exc)})


def combine_cache_lookup(payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Read only the exact world-scoped v5 recipe; no migration or fallback."""
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    identity_version = str(payload.get("recipeIdentityVersion") or payload.get("recipeKeyVersion") or RECIPE_IDENTITY_VERSION)
    key = recipe_key(a, b, world_id, identity_version)
    cached = cache_get(key, world_id, world_name)
    if not isinstance(cached, dict):
        return key, None
    report = _cached_payload_report(cached)
    if not report["ok"]:
        _quarantine_cached_recipe(world_id=world_id, recipe_key_value=key, reason="low_level_runtime_contract_invalid", details={"errors": report["errors"][:24]})
        return key, None
    return key, sanitize_recipe_for_delivery(cached)


def _failure_report(item: Mapping[str, Any], exc: BaseException, stage: str) -> dict[str, Any]:
    validation = validate_runtime_program(item)
    errors = copy.deepcopy(validation.get("errors") or [])
    targets = getattr(exc, "author_repair_targets", None)
    if isinstance(targets, list):
        errors = [copy.deepcopy(row) for row in targets if isinstance(row, Mapping)] or errors
    if not errors:
        errors = [{"path": "$", "code": "compile_or_wire_rejection", "message": str(exc)[:1800]}]
    return {
        "schema": "infini.low-level-gameplay-failure.v1",
        "stage": stage,
        "errorType": type(exc).__name__,
        "error": str(exc)[:2000],
        "errors": errors[:48],
        "validation": validation,
    }


def compile_and_validate_authored_runtime(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
    *,
    run_stage: Callable[..., Any],
) -> dict[str, Any]:
    """Validate/compile once, then use one conditional Gameplay Repair if rejected."""

    def domain_pass(item: dict[str, Any], prefix: str) -> dict[str, Any]:
        item = run_stage(prefix + "_strict_runtime_program", strict_validate_authored_item, item, a, b)
        item = run_stage(prefix + "_parent_power_context", apply_item_knowledge, item, a, b, ca, cb)
        item = run_stage(prefix + "_compile_runtime_program", attach_gameplay_and_runtime_program, item, a, b, ca, cb)
        run_stage(prefix + "_wire_boundary", validate_final_runtime_promise_boundary, item)
        return item

    authored = copy.deepcopy(data)
    try:
        return domain_pass(data, "02")
    except (PlannerUnavailable, ValueError, TypeError, RuntimeError, AssertionError) as exc:
        report = _failure_report(authored, exc, "gameplay_validation_or_compile")
    repaired = run_stage(
        "02r_conditional_gameplay_repair",
        repair_author_item_after_failure,
        authored,
        a,
        b,
        ca,
        cb,
        key,
        failure_report=report,
    )
    try:
        return domain_pass(repaired, "02r")
    except (PlannerUnavailable, ValueError, TypeError, RuntimeError, AssertionError) as exc:
        second = _failure_report(repaired, exc, "gameplay_repair_validation_or_compile")
        raise PlannerUnavailable("Gameplay Repair did not produce an executable low-level program: " + json.dumps(second["errors"][:12], ensure_ascii=False)) from exc


def combine(payload: dict[str, Any]) -> dict[str, Any]:
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    ca = canonicalize(a)
    cb = canonicalize(b)
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    identity_version = str(payload.get("recipeIdentityVersion") or payload.get("recipeKeyVersion") or RECIPE_IDENTITY_VERSION)
    key = recipe_key(a, b, world_id, identity_version)

    cached = cache_get(key, world_id, world_name)
    if isinstance(cached, dict):
        report = _cached_payload_report(cached)
        if report["ok"]:
            generation_debug.clear_combine_failure("cache_hit_delivered")
            return sanitize_recipe_for_delivery(cached)
        _quarantine_cached_recipe(world_id=world_id, recipe_key_value=key, reason="low_level_runtime_contract_invalid", details={"errors": report["errors"][:24]})

    pipeline_log: list[dict[str, Any]] = []
    data: dict[str, Any] | None = None
    lease = token = None
    if USE_LLM:
        lease, token = begin_llm_item_lease(key)

    def step(label: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        started = time.time()
        try:
            result = fn(*args, **kwargs)
            pipeline_log.append({"stage": label, "ok": True, "ms": int((time.time() - started) * 1000)})
            return result
        except Exception as exc:
            pipeline_log.append({"stage": label, "ok": False, "ms": int((time.time() - started) * 1000), "error": repr(exc)})
            generation_debug.record_combine_failure(label, exc, payload, args[0] if args and isinstance(args[0], dict) else data, pipeline_log)
            raise

    try:
        if USE_LLM:
            data = step("01_gameplay_author", try_llm_plan, a, b, ca, cb, key)
        if data is None:
            if not ALLOW_DETERMINISTIC_DEV_FALLBACK:
                raise PlannerUnavailable("Gameplay Author unavailable; craft failed and ingredients must be refunded")
            data = step("01_dev_only_low_level_fixture", deterministic_plan, a, b, ca, cb, key)

        data = compile_and_validate_authored_runtime(data, a, b, ca, cb, key, run_stage=step)
        data = step("03_result_knowledge_card", attach_result_knowledge_card, data, a, b)
        data = step("04_visual_technical_init", attach_visual, data, a, b, ca, cb)
        data = step("05_visual_director", apply_visual_director, data, a, b, ca, cb)
        data = step("06_vfx_director", attach_hybrid_vfx_manifest, data, key, "", a, b, call_llm_vfx_director if USE_LLM else None)
        data = step("07_visual_asset_runtime_gates", finalize_visual_asset_runtime_gates, data)
        data = step("08_visual_asset_generation", maybe_generate_visual_assets, data)
        data = step("09_visual_delivery_gate", assert_visual_delivery_ready, data)
        data = step("10_generated_parent_summary", attach_generated_parent_summary, data)
        data = step("11_final_normalize", final_normalize, data)
        data = step("12_final_runtime_wire_gate", validate_final_runtime_promise_boundary, data) and data
        vfx_report = _vfx_manifest_report(data)
        if not vfx_report["ok"]:
            raise PlannerUnavailable("final VFX wire rejected: " + json.dumps(vfx_report["errors"][:12], ensure_ascii=False))
        data = step("13_stage_accounting", _assert_stage_topology, data)

        recipe_meta = data.setdefault("recipeMeta", {})
        recipe_meta.update({
            "worldScoped": True,
            "worldId": world_id,
            "worldName": world_name,
            "recipeKey": key,
            "parentA": str(data.get("parentA") or ""),
            "parentB": str(data.get("parentB") or ""),
        })
        data["contractVersions"] = contract_versions_payload()
        debug = data.setdefault("debug", {})
        debug.update({
            "cacheScope": "world",
            "recipeIdentityVersion": identity_version,
            "worldId": world_id,
            "worldRecipesDir": str(world_recipe_dir(world_id)),
            "pipelineProfile": VISUAL_PIPELINE_PROFILE,
            "pipelineLog": pipeline_log,
        })
        data = asset_sync_service.attach_asset_sync_meta(data, asset_public_base_url=ASSET_PUBLIC_BASE_URL)
        data = world_storage.attach_recipe_health(
            data,
            app_version=APP_VERSION,
            contract_versions=data.get("contractVersions") if isinstance(data.get("contractVersions"), dict) else {},
            visual_report=visual_delivery_report(data),
        )
        data = sanitize_recipe_for_delivery(data)
        final_report = _cached_payload_report(data)
        if not final_report["ok"]:
            raise PlannerUnavailable("delivery payload failed low-level runtime boundary: " + json.dumps(final_report["errors"][:12], ensure_ascii=False))
        cache_put(key, a, b, data, world_id, world_name)
        generation_debug.clear_combine_failure("fresh_combine_success")
        return data
    except Exception as exc:
        if not isinstance(getattr(exc, "_infini_failure_snapshot", None), dict):
            generation_debug.record_combine_failure("unknown", exc, payload, data, pipeline_log)
        raise
    finally:
        if lease is not None and token is not None:
            end_llm_item_lease(lease, token)


def deterministic_plan(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Explicit opt-in development fixture, never a production design fallback."""
    return dev_fallback.deterministic_low_level_plan(a, b, ca, cb, key)


__all__ = [
    "combine",
    "combine_cache_lookup",
    "compile_and_validate_authored_runtime",
    "deterministic_plan",
]
