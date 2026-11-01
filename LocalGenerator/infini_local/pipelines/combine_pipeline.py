from __future__ import annotations

"""Author -> low-level runtime -> Visual -> VFX combine pipeline.

This module deliberately contains no weapon classifier, family route, semantic
lowerer, or compatibility path. Gameplay Author owns the complete bounded
runtime program. Deterministic stages only validate, compile, generate assets,
and commit a world-scoped recipe.
"""

import copy
from contextlib import ExitStack
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
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION, RUNTIME_PROGRAM_SCHEMA, RUNTIME_WIRE_SCHEMA
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.vfx.stage import attach_vfx_manifest
from infini_local.core.vfx.validation import validate_vfx_manifest_wire
from infini_local.core.vfx.contract import VFX_DIRECTOR_SCHEMA, VFX_MANIFEST_SCHEMA
from infini_local.pipelines import generation_debug
from infini_local.pipelines.author.stage import _identity_errors, compile_and_validate_authored_runtime, validate_final_runtime_wire_boundary
from infini_local.pipelines.vfx.request import call_llm_vfx_director
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.context.generated_summary import attach_generated_parent_summary
from infini_local.pipelines.author.request import try_llm_plan
from infini_local.pipelines.transport.profiles import (
    begin_llm_item_lease,
    end_llm_item_lease,
)
from infini_local.core.images.config import VISUAL_PIPELINE_PROFILE, contract_versions_payload
from infini_local.pipelines.visual.assets import equipment_overlay_requirement, finalize_visual_asset_runtime_gates
from infini_local.pipelines.visual.contract import VISUAL_KIT_SCHEMA, _validate_kit
from infini_local.pipelines.visual.delivery import assert_visual_delivery_ready, visual_delivery_report
from infini_local.pipelines.visual.stage import _apply_kit, apply_visual_director, attach_visual
from infini_local.pipelines.images.stage import maybe_generate_visual_assets, overlap_visual_images
from infini_local.services import asset_sync_service
from infini_local.services.combine_endpoint import generation_stage
from infini_local.storage import craft_progress, world_storage
from infini_local.storage.trace_runtime import trace_event
from infini_local.storage.world_storage import is_deliverable_recipe_payload, sanitize_recipe_for_delivery
from infini_local.core.item_identity_tools import item_identity
from infini_local.storage.world_recipe_runtime import (
    cache_get,
    cache_put,
    normalize_world_id_from_payload,
    recipe_key,
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


def _cached_payload_report(data: Any) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    # Structural precheck only: the mandatory visual report below owns the one
    # operation-scoped PNG assessment. Other storage callers stay strict by default.
    if not is_deliverable_recipe_payload(data, check_assets=False):
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
    vfx = validate_vfx_manifest_wire(data)
    errors.extend(copy.deepcopy(vfx.get("errors") or []))
    return {"ok": not errors, "errors": errors, "runtime": wire, "visual": visual, "vfx": vfx}


def _multi_dev_profile_id(payload: dict[str, Any]) -> str:
    if not bool(payload.get("multiDevCraft")):
        return ""
    profile_id = str(payload.get("llmProfileId") or "").strip().lower()
    if profile_id not in {"llm_1", "llm_2", "llm_3"}:
        raise ValueError("multiDevCraft requires exact llmProfileId llm_1, llm_2, or llm_3")
    return profile_id


def _progress_contracts() -> dict[str, Any]:
    return {
        **contract_versions_payload(),
        "authorSchema": RUNTIME_PROGRAM_SCHEMA,
        "wireSchema": RUNTIME_WIRE_SCHEMA,
        "visualSchema": VISUAL_KIT_SCHEMA,
        "vfxDirectorSchema": VFX_DIRECTOR_SCHEMA,
        "vfxManifestSchema": VFX_MANIFEST_SCHEMA,
        "useLlm": USE_LLM,
        "developmentFallback": ALLOW_DETERMINISTIC_DEV_FALLBACK,
    }


def _validate_saved_progress(
    progress: craft_progress.CraftProgress, stage: str, data: dict[str, Any],
    a: dict[str, Any], b: dict[str, Any], key: str,
) -> None:
    """Re-admit accepted wire without compiling, repairing or choosing a design."""
    errors = list(validate_runtime_wire(data).get("errors") or [])
    errors.extend(_identity_errors(data, a, b))
    if data.get("recipeKey") != key or not isinstance(data.get("id"), str) or not data["id"]:
        errors.append({"path": "$.recipeKey", "message": "saved item identity does not match this craft"})
    if errors:
        raise progress.invalid(json.dumps(errors[:12], ensure_ascii=False))
    if stage in {"visual", "vfx"}:
        entities = data.get("runtimeProgram", {}).get("entities", [])
        entity_ids = [str(row.get("id") or "") for row in entities if isinstance(row, dict)]
        item_body_id = next((str(row.get("id") or "") for row in entities
                             if isinstance(row, dict) and row.get("kind") == "item_body"), "")
        kit, visual_errors = _validate_kit(
            data.get("visualKit"), entity_ids, item_body_id,
            equipment_overlay_required=bool(equipment_overlay_requirement(data)["required"]), accepted_data=data,
        )
        errors.extend(visual_errors)
        if kit is not None and kit != data.get("visualKit"):
            errors.append({"path": "$.visualKit", "message": "saved accepted kit would require normalization"})
        if kit is not None:
            # Recompute only the existing technical projection for comparison.
            # Never replace the saved design or erase VFX-owned impact fields.
            projected = _apply_kit(data, kit)
            if projected["visual"] != data.get("visual"):
                errors.append({"path": "$.visual", "message": "saved visual differs from its accepted kit"})
            for expected, actual in zip(projected["runtimeProgram"]["entities"], entities):
                if any(actual.get("visual", {}).get(field) != value for field, value in expected["visual"].items()):
                    errors.append({"path": f"$.runtimeProgram.entities[{actual['id']}].visual",
                                   "message": "saved entity visual differs from its accepted kit"})
    if stage == "vfx":
        errors.extend(validate_vfx_manifest_wire(data).get("errors") or [])
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    if str(debug.get("planner") or "").startswith("llm_"):
        accepted = ("gameplay", "visual", "vfx")[:("author", "visual", "vfx").index(stage) + 1]
        accounting = debug.get("llmStageAccounting")
        if not isinstance(accounting, dict) or any(type(accounting.get(name)) is not int for name in _STAGE_KEYS):
            errors.append({"path": "$.debug.llmStageAccounting", "message": "accepted stage accounting is missing"})
        else:
            for owner, baseline, repair in (
                ("gameplay", "gameplayAuthorCalls", "gameplayRepairCalls"),
                ("visual", "visualDirectorCalls", "visualRepairCalls"),
                ("vfx", "vfxDirectorCalls", "vfxRepairCalls"),
            ):
                if accounting[baseline] != int(owner in accepted) or accounting[repair] not in ({0, 1} if owner in accepted else {0}):
                    errors.append({"path": "$.debug.llmStageAccounting", "message": f"invalid accepted {owner} stage counts"})
    if errors:
        raise progress.invalid(json.dumps(errors[:12], ensure_ascii=False))


def combine_cache_lookup(payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Read only the exact world-scoped v5 recipe; no migration or fallback."""
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    identity_version = str(payload.get("recipeIdentityVersion") or RECIPE_IDENTITY_VERSION)
    profile_id = _multi_dev_profile_id(payload)
    key = recipe_key(a, b, world_id, identity_version, profile_id)
    cached = cache_get(key, world_id, world_name, validate_payload=_cached_payload_report)
    return key, sanitize_recipe_for_delivery(cached) if isinstance(cached, dict) else None


def combine(payload: dict[str, Any]) -> dict[str, Any]:
    pipeline_log: list[dict[str, Any]] = []
    data: dict[str, Any] | None = None
    lease = token = None
    key = None

    def failure_data(args=()):
        if data is None:
            # Before Author returns there is no candidate: retain both complete
            # source inputs and the computed join, not just fn's first argument.
            # generation_debug owns the existing full snapshot/redaction/toggle.
            return {"itemA": payload.get("itemA"), "itemB": payload.get("itemB"), "recipeKey": key}
        return args[0] if args and isinstance(args[0], dict) else data

    def step(label: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        with generation_stage(label):
            try:
                result = fn(*args, **kwargs)
                pipeline_log.append({"stage": label, "ok": True, "ms": int((time.monotonic() - started) * 1000)})
                return result
            except Exception as exc:
                pipeline_log.append({"stage": label, "ok": False, "ms": int((time.monotonic() - started) * 1000), "error": repr(exc)})
                generation_debug.record_combine_failure(label, exc, payload, failure_data(args), pipeline_log)
                raise

    try:
        a = payload.get("itemA") or {}
        b = payload.get("itemB") or {}
        world_id = normalize_world_id_from_payload(payload)
        world_name = str(payload.get("worldName") or "").strip()
        identity_version = str(payload.get("recipeIdentityVersion") or RECIPE_IDENTITY_VERSION)
        profile_id = _multi_dev_profile_id(payload)
        key = recipe_key(a, b, world_id, identity_version, profile_id)
        # Recheck inside singleflight: a waiter delivers the committed winner.
        with world_storage.recipe_generation_lock(world_recipe_dir(world_id), key), ExitStack() as contexts:
            cached = cache_get(key, world_id, world_name, validate_payload=_cached_payload_report)
            if isinstance(cached, dict):
                craft_progress.discard_progress(world_recipe_dir(world_id), key)
                generation_debug.clear_combine_failure("cache_hit_delivered")
                return sanitize_recipe_for_delivery(cached)
            progress_identity = {
                "worldId": world_id, "recipeKey": key, "profileId": profile_id,
                "recipeIdentityVersion": identity_version, "itemA": a, "itemB": b,
                "contracts": _progress_contracts(),
            }
            progress = contexts.enter_context(craft_progress.track_progress(
                world_recipe_dir(world_id), key, progress_identity,
                swapped_identity={**progress_identity, "itemA": b, "itemB": a},
            ))
            saved_stage, data = progress.restore()
            if data is not None:
                # Recipes are commutative; remaining model stages still see the
                # exact original parent order, even after swapping station slots.
                if progress.parents_swapped:
                    a, b = b, a
                step("00_resume_saved_design", _validate_saved_progress, progress, saved_stage, data, a, b, key)
                data.setdefault("debug", {})["craftResume"] = {"acceptedThrough": saved_stage, "itemId": data["id"]}
                trace_event("checkpoint", "craft_progress", "Continuing the accepted craft design",
                            {"recipeKey": key, "itemId": data["id"], "acceptedThrough": saved_stage})
            # A pure image retry does not need an available text provider. Other
            # continuations acquire a fresh lease, never a saved response chain.
            if USE_LLM and saved_stage != "vfx":
                lease, token = step("00_llm_lease", begin_llm_item_lease, key, preferred_profile_id=profile_id)
            if data is None:
                if USE_LLM:
                    data = step("01_gameplay_author", try_llm_plan, a, b, key)
                if data is None:
                    if not ALLOW_DETERMINISTIC_DEV_FALLBACK:
                        raise PlannerUnavailable("Gameplay Author unavailable; craft failed and ingredients must be refunded")
                    data = step("01_dev_only_low_level_fixture", dev_fallback.deterministic_low_level_plan, a, b, key)
                data = compile_and_validate_authored_runtime(data, a, b, key, run_stage=step)
                step("03_save_author", progress.accept, "author", data)
            if saved_stage not in {"visual", "vfx"}:
                data = step("04_visual_technical_init", attach_visual, data)
                data = step("05_visual_director", apply_visual_director, data, a, b)
                step("05_save_visual", progress.accept, "visual", data)
            with overlap_visual_images(data) as pending_images:
                if saved_stage != "vfx":
                    data = step("06_vfx_director", attach_vfx_manifest, data, key, a, b, call_llm_vfx_director if USE_LLM else None)
                    step("06_save_vfx", progress.accept, "vfx", data)
                data = step("07_visual_asset_runtime_gates", finalize_visual_asset_runtime_gates, data)
                image_kwargs = {"pending": pending_images} if pending_images is not None else {}
                data = step("08_visual_asset_generation", maybe_generate_visual_assets, data, **image_kwargs)
            data = step("09_visual_delivery_gate", assert_visual_delivery_ready, data)
            data = step("10_generated_parent_summary", attach_generated_parent_summary, data)
            data = step("11_final_normalize", final_normalize, data)
            # validate_final_runtime_wire_boundary returns a report dict (or
            # raises); it never returns the payload, so do not rebind `data` here.
            step("12_final_runtime_wire_gate", validate_final_runtime_wire_boundary, data)
            assert data is not None  # stage 11 always yields a payload dict
            vfx_report = validate_vfx_manifest_wire(data)
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
                "parentIdentities": [item_identity(a), item_identity(b)],
            })
            data["contractVersions"] = contract_versions_payload()
            debug = data.setdefault("debug", {})
            debug.update({
                "cacheScope": "world",
                "recipeIdentityVersion": identity_version,
                "multiDevProfileId": profile_id,
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
            craft_progress.discard_progress(world_recipe_dir(world_id), key)
            generation_debug.clear_combine_failure("fresh_combine_success")
            return data
    except Exception as exc:
        if not isinstance(getattr(exc, "_infini_failure_snapshot", None), dict):
            generation_debug.record_combine_failure("unknown", exc, payload, failure_data(), pipeline_log)
        raise
    finally:
        if lease is not None and token is not None:
            end_llm_item_lease(lease, token)


__all__ = [
    "combine",
    "combine_cache_lookup",
]
