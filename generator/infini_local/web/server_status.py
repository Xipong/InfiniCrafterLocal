"""Read-only generator readiness and effective-configuration projection."""
from __future__ import annotations

import os
import re
from typing import Any

from infini_local.core.config_bootstrap import (
    APP_VERSION, ROOT, RECIPE_IDENTITY_VERSION, CONFIG_PATH, CACHE_DIR,
    SPRITE_DIR, WORLD_RECIPES_DIR, TERRARIA_PORT, ASSET_PUBLIC_BASE_URL, ASSET_TRANSPORT,
)
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
from infini_local.core.contract_versions import TMODLOADER_GREY_ZONE_NOTES
from infini_local.core.env_utils import env_str
from infini_local.core.image_dependencies import Image
from infini_local.core.server_endpoint import resolve_port
from infini_local.core.images import config as visual_config
from infini_local.core.llm_config import LANGUAGE, USE_LLM
from infini_local.core.vfx.config import (
    VFX_EMERGENCY_MAX_DRAW_CALLS, VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
    VFX_EMERGENCY_MAX_PARTICLES_TOTAL, VFX_LLM_DIRECTOR_ENABLED, VFX_RENDER_QUALITY,
)
from infini_local.pipelines import generation_debug
from infini_local.pipelines.images.backends import resolve_comfyui_workflow_path, sdcpp_debug_snapshot
from infini_local.pipelines.transport.client import llm_auth_snapshot
from infini_local.pipelines.transport.profiles import active_llm_provider
from infini_local.services import combine_endpoint, network_info_service


def multiplayer_connect_info() -> dict[str, Any]:
    return network_info_service.multiplayer_connect_info(
        local_generator_port=resolve_port(env_str("INFINI_PORT", "")),
        terraria_port=TERRARIA_PORT,
        asset_public_base_url=ASSET_PUBLIC_BASE_URL,
        asset_transport=ASSET_TRANSPORT,
        host=env_str("INFINI_HOST", "127.0.0.1"),
    )


def health_payload() -> dict[str, Any]:
    # Helper readiness/config must not wait on a separate image service (which
    # may be unused with Codex). Explicit /sdcpp_debug retains its live probe.
    sdcpp = sdcpp_debug_snapshot(include_log_tail=False, probe_server=False)
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
    auth = llm_auth_snapshot()
    launch_id = env_str("INFINI_STUDIO_LAUNCH_ID", "", strip=False)
    return {
        "ok": True,
        "version": APP_VERSION,
        "generationActivity": combine_endpoint.generation_activity_snapshot(),
        # Explicit partial acknowledgement: no secret values, endpoint query
        # strings or secret-derived hashes; 'auto' stays unresolved here.
        "effectiveConfig": {
            "cacheDir": str(CACHE_DIR.resolve()),
            "worldRecipesDir": str(WORLD_RECIPES_DIR.resolve()),
            "language": LANGUAGE,
            "imageBackend": visual_config.IMAGE_BACKEND,
            "llmProvider": str(auth.get("provider") or ""),
            "llmModel": str(auth.get("model") or ""),
            "openrouterProvider": str(auth.get("openrouterProvider") or ""),
            "sdcppAutostart": bool(sdcpp["autostart"]),
        },
        "serverRoot": str(ROOT),
        "configPath": str(CONFIG_PATH),
        "pid": os.getpid(),
        # Readiness correlation only, not authorization or persisted config.
        "studioLaunchId": launch_id if re.fullmatch(r"[0-9a-f]{32}", launch_id) else None,
        "useLLM": USE_LLM,
        "llmProvider": active_llm_provider(),
        "llmAuth": auth,
        "runtimeApiVersion": RUNTIME_PROGRAM_API_VERSION,
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
        "vfxContract": "exact_runtime_entity_event_pairs",
        "vfxBaselineCalls": 1,
        "vfxRepairConditional": True,
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
        "lastCombineFailure": generation_debug.last_combine_failure_summary(),
        "worldRecipesDir": str(WORLD_RECIPES_DIR),
        "recipeCacheScope": "world",
        "recipeStorage": "authoritative_world_recipe_files",
        "requiresWorldId": True,
        "recipeIdentityVersion": RECIPE_IDENTITY_VERSION,
        "assetSync": {"transport": ASSET_TRANSPORT, "endpoint": "/get_asset", "publicBaseUrl": ASSET_PUBLIC_BASE_URL, "spriteDir": str(SPRITE_DIR)},
        "multiplayer": multiplayer_connect_info(),
    }
