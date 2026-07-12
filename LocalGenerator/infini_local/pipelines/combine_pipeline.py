from __future__ import annotations

import json
import time
from typing import Any

from infini_local.core import dev_fallback

from infini_local.core.boundary_models import (
    validate_executable_item_boundary,
    validate_visual_authoring_boundaries,
)

from infini_local.core.config_bootstrap import (
    APP_VERSION,
    ASSET_PUBLIC_BASE_URL,
    RECIPE_IDENTITY_VERSION,
)
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import name_of, stable_hash
from infini_local.core.llm_config import ALLOW_DETERMINISTIC_DEV_FALLBACK, USE_LLM
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION
from infini_local.core.vfx_manifest import attach_hybrid_vfx_manifest
from infini_local.pipelines import generation_debug
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.executable_boundary_projection import project_attack_presentation_fields
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.generated_parent_summary import attach_generated_parent_summary
from infini_local.pipelines.item_power_knowledge import (
    apply_item_knowledge,
    canonicalize,
    recipe_meta,
    tags_of,
)
from infini_local.pipelines.llm_authoring_pipeline import call_llm_vfx_director, try_llm_plan
from infini_local.pipelines.pipeline_visual_config import (
    VISUAL_PIPELINE_PROFILE,
    contract_versions_payload,
)
from infini_local.pipelines.presentation_sound import attach_presentation_and_sound
from infini_local.pipelines.result_identity_policy import (
    canonical_for_result,
    category_policy,
    choose_result_category,
    creative_result_name,
    inh_for_parent,
    palette_from,
    rep,
    rep_for_parent,
    required_anchors_from,
)
from infini_local.pipelines.result_knowledge_card import attach_result_knowledge_card
from infini_local.pipelines.visual_generation_pipeline import (
    apply_visual_director,
    attach_visual,
)
from infini_local.pipelines.visual_asset_plan import finalize_visual_asset_runtime_gates
from infini_local.pipelines.visual_delivery_gate import assert_visual_delivery_ready, visual_delivery_report
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





def _validate_and_project_visual_authoring_boundaries(data: dict[str, Any]) -> dict[str, Any]:
    """Apply shape-only visual cache migration, then validate VFX authoring data."""
    normalized = validate_visual_authoring_boundaries(data)
    if "visualKit" in normalized:
        data["visualKit"] = normalized["visualKit"]
    # VFX is validated but not rewritten here: its frozen JSON is already mirrored
    # into AttackSpec for C# runtime consumption and must stay byte-consistent.
    return data

# AGENT MAP: main /combine pipeline spine. The important shape is:
# request payload -> parent/world context -> LLM or fallback authored data ->
# runtimePlan compile/repair -> balance/final normalize -> visual/assets ->
# deliverable GeneratedItemData. Stage labels in combine() are debug breadcrumbs;
# do not insert hidden gameplay authoring into cache, visual, or trace helpers.


def _quarantine_cached_recipe(
    *,
    world_id: str,
    recipe_key_value: str,
    reason: str,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        quarantined = quarantine_world_recipe_cache(
            recipe_key_value,
            world_id,
            reason,
            details=details,
        )
        if quarantined:
            trace_event(
                "warn",
                "COMBINE:cache",
                "invalid cached recipe quarantined",
                {
                    "recipeKey": recipe_key_value,
                    "worldId": world_id,
                    "reason": reason,
                    "path": quarantined,
                },
            )
    except (OSError, ValueError, TypeError) as exc:
        trace_event(
            "warn",
            "COMBINE:cache",
            "could not quarantine invalid cached recipe",
            {
                "recipeKey": recipe_key_value,
                "worldId": world_id,
                "reason": reason,
                "error": repr(exc),
            },
        )


def _cached_payload_passes_executable_boundary(
    cached: dict[str, Any],
    *,
    recipe_key_value: str,
    source: str,
) -> bool:
    """Reject stale/partial cache payloads instead of delivering silent defaults.

    Cache compatibility migration is intentionally limited to known presentation
    fields.  Any remaining executable-contract drift means the recipe must be
    regenerated from its parents; a cache hit is not permission to bypass the same
    strict Python ↔ C# boundary used by a fresh craft.
    """
    try:
        validate_executable_item_boundary(cached)
        normalized = validate_visual_authoring_boundaries(cached)
        if "visualKit" in normalized:
            cached["visualKit"] = normalized["visualKit"]
    except Exception as exc:
        trace_event(
            "step",
            "COMBINE:cache",
            "cached recipe ignored because a strict contract boundary is invalid",
            {
                "recipeKey": recipe_key_value,
                "source": str(source or "cache"),
                "error": repr(exc),
            },
        )
        return False
    return True

def combine_cache_lookup(payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Return a world-scoped cached recipe without starting generation.

    This is a transport/cache helper, not a design path: it computes the exact same
    recipe key as /combine and reads the existing world recipe file only. It is used
    so a Terraria client can recover an item after an earlier long /combine request
    timed out locally but finished and wrote the recipe on the generator side.
    """
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    recipe_identity_version = str(payload.get("recipeIdentityVersion") or payload.get("recipeKeyVersion") or RECIPE_IDENTITY_VERSION)
    key = recipe_key(a, b, world_id, recipe_identity_version)
    cached = cache_get(key, world_id, world_name)
    if isinstance(cached, dict):
        cached = project_attack_presentation_fields(cached, source="cache_lookup")
        if not _cached_payload_passes_executable_boundary(
            cached,
            recipe_key_value=key,
            source="cache_lookup",
        ):
            _quarantine_cached_recipe(
                world_id=world_id,
                recipe_key_value=key,
                reason="executable_boundary_invalid",
                details={"source": "cache_lookup"},
            )
            cached = None
    if cached is not None and not is_deliverable_recipe_payload(cached):
        source_mode = cached.get("sourceMode") if isinstance(cached, dict) else ""
        trace_event("step", "HTTP:/combine", "world recipe cache skipped non-deliverable payload", {"recipeKey": key, "sourceMode": source_mode})
        _quarantine_cached_recipe(
            world_id=world_id,
            recipe_key_value=key,
            reason="payload_not_deliverable",
            details={"sourceMode": str(source_mode or "")},
        )
        cached = None
    if cached is not None:
        visual_report = visual_delivery_report(cached, check_backend_config=False)
        if not visual_report.get("ok"):
            trace_event("step", "HTTP:/combine", "world recipe cache skipped missing required visual asset", {"recipeKey": key, "visualDelivery": visual_report})
            _quarantine_cached_recipe(
                world_id=world_id,
                recipe_key_value=key,
                reason="required_visual_asset_invalid",
                details={"problems": visual_report.get("problems") or []},
            )
            cached = None
    return key, cached

def combine(payload: dict[str, Any]) -> dict[str, Any]:
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    world_id = normalize_world_id_from_payload(payload)
    world_name = str(payload.get("worldName") or "").strip()
    recipe_identity_version = str(payload.get("recipeIdentityVersion") or payload.get("recipeKeyVersion") or RECIPE_IDENTITY_VERSION)
    key = recipe_key(a, b, world_id, recipe_identity_version)
    cached = cache_get(key, world_id, world_name)
    if isinstance(cached, dict):
        cached = project_attack_presentation_fields(cached, source="cache_delivery")
        if not _cached_payload_passes_executable_boundary(
            cached,
            recipe_key_value=key,
            source="cache_delivery",
        ):
            _quarantine_cached_recipe(
                world_id=world_id,
                recipe_key_value=key,
                reason="executable_boundary_invalid",
                details={"source": "cache_delivery"},
            )
            cached = None
    if cached:
        visual_report = visual_delivery_report(cached, check_backend_config=False)
        if visual_report.get("ok"):
            generation_debug.clear_combine_failure("cache_hit_delivered")
            return sanitize_recipe_for_delivery(cached)
        trace_event("step", "COMBINE:cache", "cached recipe ignored because required visual asset is not deliverable", {"recipeKey": key, "visualDelivery": visual_report})
        _quarantine_cached_recipe(
            world_id=world_id,
            recipe_key_value=key,
            reason="required_visual_asset_invalid",
            details={"problems": visual_report.get("problems") or []},
        )

    ca = canonicalize(a)
    cb = canonicalize(b)
    pipeline_log: list[dict[str, Any]] = []
    data: dict[str, Any] | None = None
    generation_debug.clear_combine_failure("new_combine_started")

    def step(label: str, fn, *args, **kwargs):
        t0 = time.time()
        try:
            out = fn(*args, **kwargs)
            pipeline_log.append({"stage": label, "ok": True, "ms": int((time.time() - t0) * 1000)})
            return out
        except Exception as e:
            pipeline_log.append({"stage": label, "ok": False, "ms": int((time.time() - t0) * 1000), "error": repr(e)})
            partial = args[0] if args and isinstance(args[0], dict) else data
            generation_debug.record_combine_failure(label, e, payload, partial, pipeline_log)
            raise

    try:
        if USE_LLM:
            data = step("01_author_llm_plan", try_llm_plan, a, b, ca, cb, key)

        if data is None:
            if ALLOW_DETERMINISTIC_DEV_FALLBACK:
                data = step("01b_deterministic_dev_fallback", deterministic_plan, a, b, ca, cb, key)
                data.setdefault("debug", {})["planner"] = "deterministic_dev_fallback"
            else:
                err = PlannerUnavailable("LLM planner unavailable or returned invalid output; craft failed and ingredients must be refunded")
                generation_debug.record_combine_failure("01_author_llm_plan", err, payload, data, pipeline_log)
                raise err

        # Author-first pipeline. The code is deliberately not the designer here:
        # it validates shape, computes safety envelope, asks/keeps authored toy fields,
        # then generates a visible asset pack for the authored behavior.
        data = step("02_schema_validate_and_minimal_repair", validate_and_repair, data, a, b, ca, cb, key)
        data = step("03_runtime_knowledge_context", apply_item_knowledge, data, a, b, ca, cb)
        data = step("04_author_gameplay_to_runtime_envelope", attach_gameplay_and_attack, data, a, b, ca, cb)
        data = step("04b_project_presentation_out_of_attack", project_attack_presentation_fields, data, source="post_gameplay_compile")
        step("04c_strict_executable_preflight", validate_executable_item_boundary, data)
        data = step("05_presentation_sound_from_author_intent", attach_presentation_and_sound, data)
        data = step("06_result_card_after_runtime_stats", attach_result_knowledge_card, data, a, b)
        data = step("07_item_visual_brief_preserve_author", attach_visual, data, a, b, ca, cb)
        data = step("08_visual_director_asset_pack", apply_visual_director, data, a, b, ca, cb)
        data = step("08b_project_presentation_out_of_attack", project_attack_presentation_fields, data, source="post_visual_director")
        step("08c_strict_executable_preflight", validate_executable_item_boundary, data)
        data = step("08d_hybrid_vfx_manifest", attach_hybrid_vfx_manifest, data, key, "", a, b, call_llm_vfx_director if USE_LLM else None)
        data = step("08e_visual_asset_runtime_gates", finalize_visual_asset_runtime_gates, data)
        data = step("08f_strict_visual_authoring_boundaries", _validate_and_project_visual_authoring_boundaries, data)
        data = step("09_visual_asset_generation", maybe_generate_visual_assets, data)
        data = step("09b_visual_delivery_gate", assert_visual_delivery_ready, data)
        data = step("11_generated_parent_summary", attach_generated_parent_summary, data)
        data = step("11a_project_presentation_out_of_attack", project_attack_presentation_fields, data, source="final_pre_boundary")
        step("11b_strict_executable_boundary", validate_executable_item_boundary, data)
        data = step("12_final_normalize", final_normalize, data)
        step("12b_strict_executable_boundary", validate_executable_item_boundary, data)
        data = step("12c_strict_visual_authoring_boundaries", _validate_and_project_visual_authoring_boundaries, data)
        data.setdefault("recipeMeta", {})["worldScoped"] = True
        data.setdefault("recipeMeta", {})["worldId"] = world_id
        data.setdefault("recipeMeta", {})["worldName"] = world_name
        data.setdefault("recipeMeta", {})["recipeKey"] = key
        data.setdefault("debug", {})["cacheScope"] = "world"
        data.setdefault("debug", {})["recipeIdentityVersion"] = recipe_identity_version
        data.setdefault("debug", {})["worldId"] = world_id
        data.setdefault("debug", {})["worldRecipesDir"] = str(world_recipe_dir(world_id))
        data.setdefault("debug", {})["pipelineProfile"] = VISUAL_PIPELINE_PROFILE
        data.setdefault("debug", {})["pipelineLog"] = json.dumps(pipeline_log, ensure_ascii=False)
        data = asset_sync_service.attach_asset_sync_meta(data, asset_public_base_url=ASSET_PUBLIC_BASE_URL)
        data = world_storage.attach_recipe_health(
            data,
            app_version=APP_VERSION,
            contract_versions=contract_versions_payload(),
            visual_report=visual_delivery_report(data),
        )
        data = sanitize_recipe_for_delivery(data)
        cache_put(key, a, b, data, world_id, world_name)
        generation_debug.clear_combine_failure("fresh_combine_success")
        return data
    except Exception as e:
        if not generation_debug.last_combine_failure_summary():
            generation_debug.record_combine_failure("unknown", e, payload, data, pipeline_log)
        raise

def deterministic_plan(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    """Run the explicit dev-only fallback planner.

    Normal gameplay must not use this path unless
    INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK=1 is set.  The semantic fallback
    table lives in dev_fallback.py so server.py remains the authored LLM/runtime
    transport and validation shell.
    """
    return dev_fallback.deterministic_plan(a, b, ca, cb, key, _dev_fallback_helpers())


def _dev_fallback_helpers() -> dict[str, Any]:
    """Return only the helper surface the explicit dev fallback is allowed to use."""
    return {
        "APP_VERSION": APP_VERSION,
        "ENGINE_RUNTIME_API_VERSION": ENGINE_RUNTIME_API_VERSION,
        "canonical_for_result": canonical_for_result,
        "category_policy": category_policy,
        "choose_result_category": choose_result_category,
        "creative_result_name": creative_result_name,
        "inh_for_parent": inh_for_parent,
        "name_of": name_of,
        "palette_from": palette_from,
        "recipe_meta": recipe_meta,
        "rep": rep,
        "rep_for_parent": rep_for_parent,
        "required_anchors_from": required_anchors_from,
        "stable_hash": stable_hash,
        "tags_of": tags_of,
    }


# Presentation/sound derivation helpers live in presentation_sound.py.
