from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any, Callable

from infini_local.core import dev_fallback

from infini_local.core.boundary_models import (
    ATTACK_NON_WIRE_FIELDS,
    GAMEPLAY_DEBUG_ONLY_FIELDS,
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
from infini_local.core.runtime_contracts import STRUCTURAL_RUNTIME_CONTRACT_SCHEMA
from infini_local.core.vfx_manifest import attach_hybrid_vfx_manifest
from infini_local.pipelines import generation_debug
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.combine_validation import strict_validate_authored_item, validate_and_repair
from infini_local.pipelines.executable_boundary_projection import project_attack_presentation_fields
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.generated_parent_summary import attach_generated_parent_summary
from infini_local.pipelines.item_power_knowledge import (
    apply_item_knowledge,
    canonicalize,
    recipe_meta,
    tags_of,
)
from infini_local.pipelines.llm_authoring_pipeline import (
    call_llm_vfx_director,
    final_runtime_promise_report,
    repair_author_item_after_failure,
    try_llm_plan,
    validate_final_runtime_promise_boundary,
)
from infini_local.pipelines.llm_transport import begin_llm_item_lease, end_llm_item_lease
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


_COMPILER_RECEIPT_IDENTITY_FIELDS = (
    "claimId",
    "refIndex",
    "callId",
    "field",
    "authoredExpected",
    "finalPath",
    "compiledValue",
    "status",
)


def _compiler_receipt_fingerprints(data: dict[str, Any]) -> list[str]:
    contract_candidate = data.get("runtimeContract")
    contract: dict[str, Any] = contract_candidate if isinstance(contract_candidate, dict) else {}
    rows_candidate = contract.get("finalWireReceipts")
    rows: list[Any] = rows_candidate if isinstance(rows_candidate, list) else []
    return sorted(
        json.dumps(
            {field: row.get(field) for field in _COMPILER_RECEIPT_IDENTITY_FIELDS},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
        if isinstance(row, dict)
    )


_POST_AUTHOR_MUTABLE_ATTACK_PRESENTATION_FIELDS = frozenset({
    "projectileSpritePath", "projectileSpriteUrl", "projectileSpriteStatus", "projectileSpritePrompt", "projectileSpriteScore",
    "impactSpritePath", "impactSpriteUrl", "impactSpriteStatus", "impactSpritePrompt", "impactSpriteScore",
    "childSpritePath", "childSpriteUrl", "childSpriteStatus", "childSpritePrompt", "childSpriteScore",
    "fieldSpritePath", "fieldSpriteUrl", "fieldSpriteStatus", "fieldSpritePrompt", "fieldSpriteScore",
    "visualAnimationPlan", "vfxManifestJson",
})


def _post_author_executable_projection(data: dict[str, Any]) -> dict[str, Any]:
    """Project the executable DTO that Presentation/Visual/VFX may read but not rewrite."""
    attack_candidate = data.get("attack")
    attack: dict[str, Any] = attack_candidate if isinstance(attack_candidate, dict) else {}
    gameplay_candidate = data.get("gameplay")
    gameplay: dict[str, Any] = gameplay_candidate if isinstance(gameplay_candidate, dict) else {}
    return {
        "category": deepcopy(data.get("category")),
        "gameplay": deepcopy({key: value for key, value in gameplay.items() if key not in GAMEPLAY_DEBUG_ONLY_FIELDS}),
        "accessory": deepcopy(data.get("accessory") if isinstance(data.get("accessory"), dict) else {}),
        "armor": deepcopy(data.get("armor") if isinstance(data.get("armor"), dict) else {}),
        "attack": deepcopy({
            key: value
            for key, value in attack.items()
            if key not in ATTACK_NON_WIRE_FIELDS and key not in _POST_AUTHOR_MUTABLE_ATTACK_PRESENTATION_FIELDS
        }),
    }


def _assert_post_author_executable_unchanged(expected: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    actual = _post_author_executable_projection(data)
    changed = [field for field in expected if actual.get(field) != expected.get(field)]
    if changed:
        raise PlannerUnavailable(
            "post-author presentation/assets mutated executable DTO sections: " + ", ".join(changed)
        )
    return data


def _cached_payload_passes_executable_boundary(
    cached: dict[str, Any],
    *,
    recipe_key_value: str,
    source: str,
    parent_a: dict[str, Any],
    parent_b: dict[str, Any],
    canonical_a: dict[str, Any],
    canonical_b: dict[str, Any],
) -> bool:
    """Reject stale/partial cache payloads instead of delivering silent defaults.

    Cache compatibility migration is intentionally limited to known presentation
    fields.  Any remaining executable-contract drift means the recipe must be
    regenerated from its parents; a cache hit is not permission to bypass the same
    strict Python ↔ C# boundary used by a fresh craft.
    """
    if not is_deliverable_recipe_payload(cached):
        return False
    has_runtime_contract = "runtimeContract" in cached
    runtime_contract_candidate = cached.get("runtimeContract")
    runtime_contract: dict[str, Any] = dict(runtime_contract_candidate) if isinstance(runtime_contract_candidate, dict) else {}
    if has_runtime_contract and str(runtime_contract.get("schema") or "") != STRUCTURAL_RUNTIME_CONTRACT_SCHEMA:
        trace_event(
            "step",
            "COMBINE:cache",
            "cached recipe ignored because its structural authoring schema is stale",
            {
                "recipeKey": recipe_key_value,
                "source": str(source or "cache"),
                "schema": str(runtime_contract.get("schema") or "missing"),
                "requiredSchema": STRUCTURAL_RUNTIME_CONTRACT_SCHEMA,
            },
        )
        return False
    try:
        if has_runtime_contract:
            replayed = attach_gameplay_and_attack(
                deepcopy(cached),
                parent_a,
                parent_b,
                canonical_a,
                canonical_b,
            )
            if _compiler_receipt_fingerprints(replayed) != _compiler_receipt_fingerprints(cached):
                raise ValueError("cached compiler provenance receipts do not match a fresh structural replay")
            validate_final_runtime_promise_boundary(cached)
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
    ca = canonicalize(a)
    cb = canonicalize(b)
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
            parent_a=a,
            parent_b=b,
            canonical_a=ca,
            canonical_b=cb,
        ):
            _quarantine_cached_recipe(
                world_id=world_id,
                recipe_key_value=key,
                reason="executable_boundary_invalid",
                details={"source": "cache_lookup"},
            )
            cached = None
    if cached is not None and not is_deliverable_recipe_payload(cached):
        source_mode = cached.get("sourceMode")
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


def _best_effort_final_wire_preview(
    item: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    """Compile a diagnostic deepcopy so one scoped repair sees later wire failures too."""
    candidate = deepcopy(item)
    try:
        candidate = validate_and_repair(candidate, a, b, ca, cb, key)
        candidate = apply_item_knowledge(candidate, a, b, ca, cb)
        candidate = attach_gameplay_and_attack(candidate, a, b, ca, cb)
        candidate = project_attack_presentation_fields(candidate, source="author_failure_compiler_preview")
        return final_runtime_promise_report(candidate)
    except (PlannerUnavailable, ValueError, TypeError) as exc:
        return {
            "schema": "infini.structural-runtime-contract-report.v1",
            "ok": False,
            "finalWireReceipts": [],
            "previewError": str(exc),
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
    """Run one strict author transaction plus at most one scoped repair patch."""
    state: dict[str, Any] = {
        "data": data,
        "authorSource": deepcopy(data),
        "stage": "strict_author_validation",
    }

    def domain_pass(item: dict[str, Any], *, repaired: bool) -> dict[str, Any]:
        labels = (
            {
                "validate": "04f_repaired_strict_author_validation",
                "knowledge": "04g_repaired_runtime_knowledge_context",
                "compile": "04h_repaired_gameplay_to_runtime_envelope",
                "project": "04i_repaired_project_presentation_out_of_attack",
                "strict": "04j_repaired_strict_executable_preflight",
                "wire": "04k_repaired_structural_final_wire_preflight",
            }
            if repaired
            else {
                "validate": "02_strict_author_validation",
                "knowledge": "03_runtime_knowledge_context",
                "compile": "04_author_gameplay_to_runtime_envelope",
                "project": "04b_project_presentation_out_of_attack",
                "strict": "04c_strict_executable_preflight",
                "wire": "04d_structural_final_wire_preflight",
            }
        )
        state["stage"] = "strict_author_validation"
        item = run_stage(labels["validate"], strict_validate_authored_item, item, a, b)
        state["data"] = item
        state["authorSource"] = deepcopy(item)
        state["stage"] = "result_envelope_projection"
        item = validate_and_repair(item, a, b, ca, cb, key)
        state["data"] = item
        state["stage"] = "runtime_knowledge"
        item = run_stage(labels["knowledge"], apply_item_knowledge, item, a, b, ca, cb)
        state["data"] = item
        state["stage"] = "compiler"
        item = run_stage(labels["compile"], attach_gameplay_and_attack, item, a, b, ca, cb)
        state["data"] = item
        item = run_stage(
            labels["project"],
            project_attack_presentation_fields,
            item,
            source="post_same_author_repair_compile" if repaired else "post_gameplay_compile",
        )
        state["data"] = item
        state["stage"] = "executable_boundary"
        run_stage(labels["strict"], validate_executable_item_boundary, item)
        state["stage"] = "final_wire"
        run_stage(labels["wire"], validate_final_runtime_promise_boundary, item)
        return item

    try:
        return domain_pass(data, repaired=False)
    except PlannerUnavailable as exc:
        failed_candidate = state.get("data")
        failed: dict[str, Any] = failed_candidate if isinstance(failed_candidate, dict) else data
        failure_report: dict[str, Any] = {
            "schema": "infini.authoring-failure-report.v1",
            "stage": str(state.get("stage") or "unknown"),
            "errorType": type(exc).__name__,
            "error": str(exc)[:2000],
        }
        if exc.author_repair_rejected_domains:
            failure_report["authorRepairRejectedDomains"] = deepcopy(
                exc.author_repair_rejected_domains
            )
        if failure_report["stage"] == "final_wire":
            failure_report["finalWire"] = final_runtime_promise_report(failed)
        else:
            failure_report["compilerFinalWirePreview"] = _best_effort_final_wire_preview(
                failed, a, b, ca, cb, key,
            )
        debug_candidate = failed.get("debug")
        debug: dict[str, Any] = debug_candidate if isinstance(debug_candidate, dict) else {}
        for field in (
            "plannerPromiseGate",
            "authorItemV3LocalStrictBoundary",
            "runtimePlanValidationBeforeRepair",
            "runtimePlanRawStrictBoundary",
            "authorRepairRejectedDomains",
        ):
            if field in debug:
                diagnostic = debug[field]
                if isinstance(diagnostic, str):
                    try:
                        diagnostic = json.loads(diagnostic)
                    except (json.JSONDecodeError, TypeError):
                        pass
                failure_report[field] = diagnostic

    author_source_candidate = state.get("authorSource")
    author_source: dict[str, Any] = (
        author_source_candidate
        if isinstance(author_source_candidate, dict)
        else data
    )
    repaired_item = run_stage(
        "04e_same_author_scoped_repair",
        repair_author_item_after_failure,
        author_source,
        a,
        b,
        ca,
        cb,
        key,
        failure_report=failure_report,
    )
    return domain_pass(repaired_item, repaired=True)

def combine(payload: dict[str, Any]) -> dict[str, Any]:
    a = payload.get("itemA") or {}
    b = payload.get("itemB") or {}
    ca = canonicalize(a)
    cb = canonicalize(b)
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
            parent_a=a,
            parent_b=b,
            canonical_a=ca,
            canonical_b=cb,
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

    pipeline_log: list[dict[str, Any]] = []
    data: dict[str, Any] | None = None
    llm_lease = None
    llm_lease_token = None
    if USE_LLM:
        llm_lease, llm_lease_token = begin_llm_item_lease(key)

    def step(label: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
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
                fallback = step("01b_deterministic_dev_fallback", deterministic_plan, a, b, ca, cb, key)
                if not isinstance(fallback, dict):
                    raise PlannerUnavailable("deterministic dev fallback returned a non-object")
                data = fallback
                data.setdefault("debug", {})["planner"] = "deterministic_dev_fallback"
            else:
                err = PlannerUnavailable("LLM planner unavailable or returned invalid output; craft failed and ingredients must be refunded")
                generation_debug.record_combine_failure("01_author_llm_plan", err, payload, data, pipeline_log)
                raise err

        assert isinstance(data, dict)
        # Author-first pipeline. The code is deliberately not the designer here:
        # it validates shape, computes safety envelope, asks/keeps authored toy fields,
        # then generates a visible asset pack for the authored behavior.
        data = compile_and_validate_authored_runtime(
            data,
            a,
            b,
            ca,
            cb,
            key,
            run_stage=step,
        )
        data = step("05_presentation_sound_from_author_intent", attach_presentation_and_sound, data)
        if not isinstance(data, dict):
            raise PlannerUnavailable("presentation/sound stage returned a non-object")
        post_author_executable = _post_author_executable_projection(data)
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
        if not isinstance(data, dict):
            raise PlannerUnavailable("final normalization returned a non-object")
        data = step(
            "12aa_post_author_executable_freeze",
            _assert_post_author_executable_unchanged,
            post_author_executable,
            data,
        )
        step("12a_final_runtime_promise_boundary", validate_final_runtime_promise_boundary, data)
        step("12b_strict_executable_boundary", validate_executable_item_boundary, data)
        data = step("12c_strict_visual_authoring_boundaries", _validate_and_project_visual_authoring_boundaries, data)
        if not isinstance(data, dict):
            raise PlannerUnavailable("final visual projection returned a non-object")
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
        if not isinstance(data, dict):
            raise PlannerUnavailable("delivery sanitizer returned a non-object")
        cache_put(key, a, b, data, world_id, world_name)
        generation_debug.clear_combine_failure("fresh_combine_success")
        return data
    except Exception as e:
        if not isinstance(getattr(e, "_infini_failure_snapshot", None), dict):
            generation_debug.record_combine_failure("unknown", e, payload, data, pipeline_log)
        raise
    finally:
        if llm_lease is not None and llm_lease_token is not None:
            end_llm_item_lease(llm_lease, llm_lease_token)

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
