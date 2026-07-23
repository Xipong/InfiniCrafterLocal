from __future__ import annotations

import json
import os
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from infini_local.core.env_utils import env_int, env_str
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.config_bootstrap import (
    APP_VERSION,
    ROOT,
    RECIPE_IDENTITY_VERSION,
    DATA_DIR,
    CONFIG_PATH,
    CACHE_DIR,
    SPRITE_DIR,
    WORLD_RECIPES_DIR,
    TERRARIA_PORT,
    ASSET_PUBLIC_BASE_URL,
    ASSET_TRANSPORT,
)
from infini_local.core.contract_versions import TMODLOADER_GREY_ZONE_NOTES
from infini_local.core.effect_catalog import (
    ATTACK_PATTERN_IDS,
)
from infini_local.core.item_identity_tools import (
    item_field,
)
from infini_local.core.llm_config import (
    ALLOW_DETERMINISTIC_DEV_FALLBACK,
    LLM_MAX_TOKENS,
    LLM_PROVIDER,
    LLM_REASONING_EXCLUDE,
    LLM_REASONING_MAX_TOKENS,
    LLM_REASONING_MODE,
    LLM_LOCAL_REASONING_PROMPT,
    LLM_RESPONSE_FORMAT_MODE,
    LMSTUDIO_MODEL,
    LMSTUDIO_URL,
    OPENAI_COMPAT_API_KEY,
    OPENAI_COMPAT_BASE_URL,
    OPENAI_COMPAT_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_MODEL,
    USE_LLM,
)
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION
from infini_local.pipelines.pipeline_runtime_constants import (
    LLM_RUNTIME_AUTHORING,
    LLM_RUNTIME_PLAN_REQUIRED,
    LLM_RUNTIME_STRICT_VALIDATION,
)
from infini_local.core.vfx_manifest_config import (
    VFX_EMERGENCY_MAX_DRAW_CALLS,
    VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
    VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
    VFX_LLM_DIRECTOR_ENABLED,
    VFX_PARENT_EFFECT_INHERITANCE,
    VFX_RENDER_QUALITY,
    VFX_SELECTOR_ENABLED,
    VFX_SELECTOR_TOP,
    VFX_SLOT_MACROS,
)
from infini_local.core.vfx_recipe_library import get_vfx_recipes
from infini_local.pipelines.combine_pipeline import (
    combine,
    combine_cache_lookup,
)
from infini_local.pipelines.image_backend_pipeline import (
    ensure_sdcpp_server,
    resolve_comfyui_workflow_path,
    sdcpp_debug_snapshot,
)
from infini_local.pipelines.llm_transport import (
    active_llm_provider,
    llm_auth_snapshot,
    resolve_llm_model,
)
from infini_local.pipelines.sprite_postprocess import (
    alpha_stats,
)
from infini_local.pipelines.visual_delivery_gate import VisualDeliveryBlocked
from infini_local.pipelines.visual_generation_pipeline import build_image_prompt
from infini_local.pipelines.visual_prompt_contracts import asset_negative_prompt, normalize_asset_prompt
from infini_local.pipelines.visual_sprite_generation import generate_visual_asset, maybe_generate_sprite
from infini_local.services import (
    asset_sync_service,
    combine_endpoint,
    network_info_service,
    runtime_dump_service,
)
from infini_local.storage.trace_runtime import (
    _tail_ndjson,
    _trace_clip,
    initialize_trace_storage,
    log_event,
    PROMPT_TRACE_FILE,
    trace_event,
    TRACE_EVENTS_TAIL,
    TRACE_FILE,
    TRACE_MAX_PROMPT_CHARS,
    TRACE_PROMPTS_ENABLED,
)
from infini_local.storage.world_recipe_runtime import (
    normalize_world_id_from_payload,
    read_json_file,
    read_world_recipe_cache,
    sanitize_recipe_for_delivery,
    WorldScopeMissing,
    write_world_recipe_cache,
)
from infini_local.web import (
    trace_dashboard,
)
from infini_local.web.http_response_helpers import (
    _ascii_reason,
    _combine_failure_http_response,
    _combine_failure_payload,
    _is_client_disconnect,
)
from infini_local.web.server_trace_snapshot import (
    build_trace_snapshot,
    render_trace_snapshot_html,
)
from infini_local.web.server_utility_routes import (
    ServerUtilityRoutes,
)
from infini_local.web.vfx_debug_routes import (
    VfxDebugRoutes,
)
from infini_local.web.server_handler import build_handler
from infini_local.pipelines import generation_debug
from infini_local.pipelines import pipeline_visual_config as visual_config
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.pipeline_visual_config import cleanup_sdcpp_server_process


def load_json_file(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        trace_event("warn", "SERVER:load_json_file", "json reference load failed", {"path": str(path)}, error=repr(exc))
    return fallback

# v0.3.14: the LLM no longer receives the verbose effect-archetype library.
# It only sees a compact enum contract. The detailed JSON file remains as human/reference data,
# but runtime code uses the stable ids from effect_catalog.py.
EFFECT_ARCHETYPES = load_json_file(DATA_DIR / "effect_archetypes.json", {"patterns": {}})
ATTACK_PATTERN_NAMES = list(ATTACK_PATTERN_IDS)

# =============================================================================
# NAV: CONFIG_AND_DATA_BOOTSTRAP
# =============================================================================
# Bootstrap paths/env are imported from infini_local.core.config_bootstrap.


# =============================================================================
# NAV: VFX_MANIFEST_PIPELINE_IMPORT
# =============================================================================
# Keep the heavy VFX manifest compiler out of server.py. server.py remains the HTTP/entrypoint shell.


def _multiplayer_connect_info() -> dict[str, Any]:
    return network_info_service.multiplayer_connect_info(
        local_generator_port=env_int("INFINI_PORT", 5055, lo=1, hi=65535),
        terraria_port=TERRARIA_PORT,
        asset_public_base_url=ASSET_PUBLIC_BASE_URL,
        asset_transport=ASSET_TRANSPORT,
        host=env_str("INFINI_HOST", "127.0.0.1"),
    )



# Visual/image/sd.cpp config and lifecycle are owned by pipelines/pipeline_visual_config.py.




# =============================================================================
# NAV: RUNTIME_DUMPS_AND_ITEM_LOOKUP
# =============================================================================
# Runtime item knowledge helpers live in pipelines/item_power_knowledge.py.

# Runtime dumps are optional, but when present they are the best source of truth
# for the user's actual loaded Terraria/tModLoader mod set. They are not a hand
# dataset: they are generated by /infinidump from live Item/Projectile fields.
# Do NOT bundle personal dumps in release archives: the server can auto-discover
# dumps created by the in-game /infinidump command or use explicit env paths.
def _runtime_dump_candidates(filename: str, explicit_env: str, legacy_env: str) -> list[Path]:
    return runtime_dump_service.runtime_dump_candidates(DATA_DIR, filename, explicit_env, legacy_env)


def _resolve_runtime_dump_path(filename: str, explicit_env: str, legacy_env: str) -> Path:
    return runtime_dump_service.resolve_runtime_dump_path(DATA_DIR, filename, explicit_env, legacy_env)


ITEMS_RUNTIME_DUMP_PATH = _resolve_runtime_dump_path("items_runtime_dump.jsonl", "INFINI_ITEMS_RUNTIME_DUMP", "INFINI_ITEMS_DUMP")
PROJECTILES_RUNTIME_DUMP_PATH = _resolve_runtime_dump_path("projectiles_runtime_dump.jsonl", "INFINI_PROJECTILES_RUNTIME_DUMP", "INFINI_PROJECTILES_DUMP")


def load_jsonl_index(path: Path, key_fields: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[Any, dict[str, Any]], dict[str, dict[str, Any]]]:
    return runtime_dump_service.load_jsonl_index(path, key_fields)


RUNTIME_ITEMS, RUNTIME_ITEMS_BY_TYPE, RUNTIME_ITEMS_BY_NAME = load_jsonl_index(ITEMS_RUNTIME_DUMP_PATH, ("sourceMod", "internalName"))
RUNTIME_PROJECTILES, RUNTIME_PROJECTILES_BY_TYPE, RUNTIME_PROJECTILES_BY_NAME = load_jsonl_index(PROJECTILES_RUNTIME_DUMP_PATH, ("sourceMod", "internalName"))


def runtime_item_lookup(item: dict[str, Any]) -> dict[str, Any]:
    return runtime_dump_service.runtime_item_lookup(
        item,
        RUNTIME_ITEMS_BY_TYPE,
        RUNTIME_ITEMS_BY_NAME,
        item_field=item_field,
    )


def runtime_projectile_lookup(type_id: Any) -> dict[str, Any]:
    return runtime_dump_service.runtime_projectile_lookup(type_id, RUNTIME_PROJECTILES_BY_TYPE)


try:
    from PIL import Image, ImageDraw, ImageFilter
    PILLOW_IMPORT_ERROR = ""
except Exception as _pillow_error:
    # Pillow is a hard requirement for generated sprites by default. We keep the module importable
    # for tooling/tests, but main() refuses to run visual backends without it.
    Image = None
    ImageDraw = None
    ImageFilter = None
    PILLOW_IMPORT_ERROR = repr(_pillow_error)

# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------


# =============================================================================
# NAV: WORLD_CACHE_AND_STORAGE
# =============================================================================


def trace_snapshot() -> dict[str, Any]:
    return build_trace_snapshot(
        app_version=APP_VERSION,
        root=ROOT,
        config_path=CONFIG_PATH,
        cache_dir=CACHE_DIR,
        recipe_identity_version=RECIPE_IDENTITY_VERSION,
        world_recipes_dir=WORLD_RECIPES_DIR,
        use_llm=USE_LLM,
        llm_runtime_authoring=LLM_RUNTIME_AUTHORING,
        llm_runtime_plan_required=LLM_RUNTIME_PLAN_REQUIRED,
        image_backend=visual_config.IMAGE_BACKEND,
        visual_asset_mode=visual_config.VISUAL_ASSET_MODE,
        visual_director_llm=visual_config.VISUAL_DIRECTOR_LLM,
        vfx_llm_director_enabled=VFX_LLM_DIRECTOR_ENABLED,
        openrouter_model=OPENROUTER_MODEL,
        openai_compat_model=OPENAI_COMPAT_MODEL,
        lmstudio_model=LMSTUDIO_MODEL,
        trace_prompts_enabled=TRACE_PROMPTS_ENABLED,
        trace_max_prompt_chars=TRACE_MAX_PROMPT_CHARS,
        trace_events_tail=TRACE_EVENTS_TAIL,
        prompt_trace_file=PROMPT_TRACE_FILE,
        trace_file=TRACE_FILE,
        last_combine_failure_file=generation_debug.LAST_COMBINE_FAILURE_FILE,
        last_combine_failure_summary=generation_debug.last_combine_failure_summary,
        active_llm_provider=active_llm_provider,
        llm_auth_snapshot=llm_auth_snapshot,
        contract_versions_payload=visual_config.contract_versions_payload,
        sdcpp_debug_snapshot=sdcpp_debug_snapshot,
        tail_ndjson=_tail_ndjson,
    )


def trace_snapshot_html() -> str:
    return render_trace_snapshot_html(
        trace_snapshot(),
        app_version=APP_VERSION,
        trace_clip=_trace_clip,
    )


# -----------------------------------------------------------------------------
# Canonicalization
# -----------------------------------------------------------------------------


# =============================================================================
# NAV: ITEM_FINGERPRINT_AND_SIGNALS
# =============================================================================


# Item signal/knowledge functions live in pipelines/item_power_knowledge.py.

# -----------------------------------------------------------------------------
# Planner / resolver
# -----------------------------------------------------------------------------


# =============================================================================
# NAV: GAMEPLAY_AND_ATTACK_PIPELINE
# =============================================================================


# DEV-only fallback base/tool/weapon plan builders live in dev_fallback.py.
# Normal generation enters via try_llm_plan() and the runtime_authoring package.


# =============================================================================
# NAV: CATEGORY_AND_POLICY
# =============================================================================


# DEV-only accessory fallback builder lives in dev_fallback.py.


# Runtime enums, codebooks and planner field limits are owned by pipelines/pipeline_runtime_constants.py.


# -----------------------------------------------------------------------------
# Sprite generation / judge / postprocess
# -----------------------------------------------------------------------------


# =============================================================================
# NAV: VISUAL_ASSET_PIPELINE
# =============================================================================


# =============================================================================
# NAV: VFX_MANIFEST_PIPELINE
# =============================================================================
# The VFX manifest package owns generation-time VFX assembly.


# =============================================================================
# NAV: FINAL_NORMALIZE_AND_HTTP
# =============================================================================


# -----------------------------------------------------------------------------
# HTTP server
# -----------------------------------------------------------------------------


def _health_payload() -> dict[str, Any]:
    sdcpp = sdcpp_debug_snapshot(include_log_tail=False)
    sdcpp.update({
        "mode": "server",
        "serverAutostart": sdcpp["autostart"],
        "lastCommand": sdcpp["command"],
        "size": [visual_config.SDCPP_WIDTH, visual_config.SDCPP_HEIGHT],
        "steps": visual_config.SDCPP_STEPS,
        "cfg": visual_config.SDCPP_CFG,
        "sampler": visual_config.SDCPP_SAMPLER,
        "timeout": visual_config.SDCPP_TIMEOUT,
        "serverTimeout": visual_config.SDCPP_SERVER_REQUEST_TIMEOUT,
    })
    visual_director_configured = bool(visual_config.VISUAL_DIRECTOR_LLM)
    visual_director_active = bool(USE_LLM and visual_config.VISUAL_DIRECTOR_LLM)
    vfx_llm_director_configured = bool(VFX_LLM_DIRECTOR_ENABLED)
    vfx_llm_director_active = bool(USE_LLM and VFX_LLM_DIRECTOR_ENABLED)
    return {
        "ok": True,
        "version": APP_VERSION,
        "serverRoot": str(ROOT),
        "configPath": str(CONFIG_PATH),
        "pid": os.getpid(),
        "useLLM": USE_LLM,
        "llmProvider": active_llm_provider(),
        "llmAuth": llm_auth_snapshot(),
        "llmRuntimeAuthoring": LLM_RUNTIME_AUTHORING,
        "llmRuntimePlanRequired": LLM_RUNTIME_PLAN_REQUIRED,
        "llmRuntimeStrictValidation": LLM_RUNTIME_STRICT_VALIDATION,
        "runtimeApiVersion": ENGINE_RUNTIME_API_VERSION,
        "contractVersions": visual_config.contract_versions_payload(),
        "tmodloaderGreyZoneNotes": TMODLOADER_GREY_ZONE_NOTES,
        "imageBackend": visual_config.IMAGE_BACKEND,
        "imageBackendRaw": visual_config.IMAGE_BACKEND_RAW,
        "imageBackendConfigError": visual_config.IMAGE_BACKEND_CONFIG_ERROR,
        "visualAssetMode": visual_config.VISUAL_ASSET_MODE,
        "visualDirectorLLM": visual_config.VISUAL_DIRECTOR_LLM,
        "visualDirectorLLMConfigured": visual_director_configured,
        "visualDirectorLLMActive": visual_director_active,
        "vfxLlmDirectorConfigured": vfx_llm_director_configured,
        "vfxLlmDirectorActive": vfx_llm_director_active,
        "visualPipelineProfile": visual_config.VISUAL_PIPELINE_PROFILE,
        "visualGenerationTimeout": visual_config.VISUAL_GENERATION_TIMEOUT,
        "visualRequireItemSprite": visual_config.VISUAL_REQUIRE_ITEM_SPRITE,
        "visualRequireZImageBackend": visual_config.VISUAL_REQUIRE_ZIMAGE_BACKEND,
        "zImagePromptContract": visual_config.ZIMAGE_PROMPT_CONTRACT,
        "zImagePositiveOnly": visual_config.ZIMAGE_POSITIVE_ONLY,
        "patternLibraryCards": visual_config.PATTERN_LIBRARY_CARDS,
        "patternRepairAttempts": visual_config.PATTERN_REPAIR_ATTEMPTS,
        "vfxSelector": VFX_SELECTOR_ENABLED,
        "vfxRecipeCount": len(get_vfx_recipes()),
        "vfxMacroCount": len(VFX_SLOT_MACROS),
        "vfxSelectorTop": VFX_SELECTOR_TOP,
        "vfxParentEffectInheritance": VFX_PARENT_EFFECT_INHERITANCE,
        "vfxRenderQuality": VFX_RENDER_QUALITY,
        "vfxEmergencyCaps": {
            "maxParticlesPerTick": VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
            "maxParticlesTotal": VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
            "maxDrawCalls": VFX_EMERGENCY_MAX_DRAW_CALLS,
        },
        "removeBg": visual_config.REMOVE_BG,
        "requirePillow": visual_config.REQUIRE_PILLOW,
        "pillowAvailable": Image is not None,
        "bgRemoveMode": visual_config.BG_REMOVE_MODE,
        "bgColor": visual_config.BG_COLOR,
        "a1111Size": [visual_config.A1111_WIDTH, visual_config.A1111_HEIGHT],
        "comfyui": {
            "url": visual_config.COMFYUI_URL,
            "workflow": str(resolve_comfyui_workflow_path() or visual_config.COMFYUI_WORKFLOW),
            "checkpoint": visual_config.COMFYUI_CHECKPOINT,
            "lora": visual_config.COMFYUI_LORA_NAME,
            "size": [visual_config.COMFYUI_WIDTH, visual_config.COMFYUI_HEIGHT],
            "steps": visual_config.COMFYUI_STEPS,
            "cfg": visual_config.COMFYUI_CFG,
            "sampler": visual_config.COMFYUI_SAMPLER,
            "scheduler": visual_config.COMFYUI_SCHEDULER,
        },
        "sdcpp": sdcpp,
        "imageVariants": visual_config.GENERATE_VARIANTS,
        "spriteRetries": visual_config.SPRITE_RETRIES,
        "spriteValidation": {
            "minBboxRatio": visual_config.SPRITE_MIN_BBOX_RATIO,
            "maxBboxRatio": visual_config.SPRITE_MAX_BBOX_RATIO,
            "minOpaquePct": visual_config.SPRITE_MIN_OPAQUE_PCT,
            "maxOpaquePct": visual_config.SPRITE_MAX_OPAQUE_PCT,
        },
        "deterministicDevFallback": ALLOW_DETERMINISTIC_DEV_FALLBACK,
        "lastCombineFailure": generation_debug.last_combine_failure_summary(),
        "worldRecipesDir": str(WORLD_RECIPES_DIR),
        "recipeCacheScope": "world",
        "recipeStorage": "authoritative_world_recipe_files",
        "requiresWorldId": True,
        "recipeIdentityVersion": RECIPE_IDENTITY_VERSION,
        "assetSync": {"transport": ASSET_TRANSPORT, "endpoint": "/get_asset", "publicBaseUrl": ASSET_PUBLIC_BASE_URL, "spriteDir": str(SPRITE_DIR)},
        "multiplayer": _multiplayer_connect_info(),
    }


def _utility_routes() -> ServerUtilityRoutes:
    return ServerUtilityRoutes(
        app_version=APP_VERSION,
        root=ROOT,
        cache_dir=CACHE_DIR,
        sprite_dir=SPRITE_DIR,
        world_recipes_dir=WORLD_RECIPES_DIR,
        trace_files=(TRACE_FILE, PROMPT_TRACE_FILE, CACHE_DIR / "events.ndjson"),
        trace_dashboard=trace_dashboard,
        asset_sync_service=asset_sync_service,
        health_payload=_health_payload,
        multiplayer_connect_info=_multiplayer_connect_info,
        trace_snapshot=trace_snapshot,
        trace_snapshot_html=trace_snapshot_html,
        trace_event=trace_event,
        sdcpp_start=ensure_sdcpp_server,
        sdcpp_debug_snapshot=sdcpp_debug_snapshot,
        read_json_file=read_json_file,
        last_combine_failure_payload=generation_debug.last_combine_failure_payload,
        cleanup_for_shutdown=cleanup_sdcpp_server_process,
        build_image_prompt=build_image_prompt,
        maybe_generate_sprite=maybe_generate_sprite,
        normalize_asset_prompt=normalize_asset_prompt,
        generate_visual_asset=generate_visual_asset,
        asset_negative_prompt=asset_negative_prompt,
        alpha_stats=alpha_stats,
        image_module=Image,
    )

def _vfx_debug_routes() -> VfxDebugRoutes:
    return VfxDebugRoutes(
        app_version=APP_VERSION,
        normalize_world_id_from_payload=normalize_world_id_from_payload,
        read_world_recipe_cache=read_world_recipe_cache,
        write_world_recipe_cache=write_world_recipe_cache,
        final_normalize=final_normalize,
    )


# Pipeline modules use explicit imports; server.py stays as HTTP shell/wiring.


Handler = build_handler(
    app_version=APP_VERSION,
    utility_routes=_utility_routes,
    vfx_debug_routes=_vfx_debug_routes,
    combine_endpoint=combine_endpoint,
    combine_cache_lookup=combine_cache_lookup,
    sanitize_recipe_for_delivery=sanitize_recipe_for_delivery,
    combine=combine,
    trace_event=trace_event,
    log_event=log_event,
    is_client_disconnect=_is_client_disconnect,
    world_scope_missing=WorldScopeMissing,
    visual_delivery_blocked=VisualDeliveryBlocked,
    planner_unavailable=PlannerUnavailable,
    last_combine_failure_summary=generation_debug.last_combine_failure_summary,
    clear_combine_failure=generation_debug.clear_combine_failure,
    combine_failure_http_response=_combine_failure_http_response,
    combine_failure_payload=_combine_failure_payload,
    ascii_reason=_ascii_reason,
)


def main() -> None:
    # Autostart happens in ThreadingHTTPServer workers, where Python forbids
    # signal registration. Install the process-tree cleanup on the main thread
    # before any request can launch sd.cpp.
    initialize_trace_storage()
    visual_config.install_sdcpp_cleanup_handlers()
    if visual_config.REQUIRE_PILLOW and Image is None and env_str("INFINI_IMAGE_BACKEND", visual_config.IMAGE_BACKEND).lower() != "off":
        raise SystemExit("Pillow is required for InfiniCrafterLocal visual generation/postprocess. Run 02_INSTALL_LOCAL_GENERATOR.bat. Import error: " + PILLOW_IMPORT_ERROR)
    host = env_str("INFINI_HOST", "127.0.0.1")
    port = env_int("INFINI_PORT", 5055, lo=1, hi=65535)
    print(f"InfiniCrafterLocal v{APP_VERSION} listening on http://{host}:{port}")
    print(f"LLM={USE_LLM} provider={active_llm_provider()} model={resolve_llm_model() if USE_LLM else '<off>'} deterministicDevFallback={ALLOW_DETERMINISTIC_DEV_FALLBACK} imageBackend={visual_config.IMAGE_BACKEND} worldRecipes={WORLD_RECIPES_DIR}")
    if visual_config.IMAGE_BACKEND in {"sdcpp", "stablediffusioncpp", "stable-diffusion.cpp", "stable_diffusion_cpp"}:
        print(f"stable-diffusion.cpp server={visual_config.SDCPP_SERVER_URL} autostart={visual_config.SDCPP_SERVER_AUTOSTART} exe={visual_config.SDCPP_SERVER_EXE or '<external>'} model={visual_config.SDCPP_MODEL or '<external>'} steps={visual_config.SDCPP_STEPS} cfg={visual_config.SDCPP_CFG} size={visual_config.SDCPP_WIDTH}x{visual_config.SDCPP_HEIGHT}")
    if USE_LLM:
        print("Tip: set INFINI_LLM_PROVIDER=openrouter + INFINI_OPENROUTER_API_KEY + INFINI_OPENROUTER_MODEL to use OpenRouter instead of LM Studio.")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
