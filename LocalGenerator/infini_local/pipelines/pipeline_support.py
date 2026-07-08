from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import queue
import random
import re
import shlex
import time
import traceback
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from infini_local.core.env_utils import env_bool, env_float, env_int, env_str, env_first, env_path
from infini_local.core.config_bootstrap import (
    APP_VERSION,
    ASSET_PUBLIC_BASE_URL,
    CACHE_DIR,
    CONFIG_PATH,
    DATA_DIR,
    RECIPE_IDENTITY_VERSION,
    ROOT,
    SPRITE_DIR,
    TERRARIA_PORT,
    WORLD_RECIPES_DIR,
)
from infini_local.core.category_policy import (
    ACCESSORY_HINT_TAGS,
    ALLOWED_CATEGORIES,
    AMMO_HINT_TAGS,
    ARMOR_HINT_TAGS,
    COMBAT_CATEGORIES,
    NON_WEAPON_CATEGORIES,
    PLACEABLE_HINT_TAGS,
    STRONG_ACCESSORY_TAGS,
    TOOL_HINT_TAGS,
    WEAPON_UPGRADE_TAGS,
)
from infini_local.core.item_signals import HARD_TAGS, VISUAL_SYNONYMS, knowledge_key, wire_identity_names
from infini_local.core.effect_catalog import (
    ATTACK_PATTERN_IDS,
    attack_pattern_contract_for_llm,
    normalize_attack_pattern,
    pattern_card,
    resolve_attack_pattern,
    select_pattern_cards,
)
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib.parse import urlparse, parse_qs, urlencode


def load_json_file(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
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
from infini_local.core.vfx_manifest import (
    VFX_EMERGENCY_MAX_DRAW_CALLS,
    VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
    VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
    VFX_LLM_DIRECTOR_ENABLED,
    VFX_MAGNITUDE_CLASSES,
    VFX_MORPH_RECIPES_RAW,
    VFX_PARENT_EFFECT_INHERITANCE,
    VFX_PARENT_EFFECT_WEIGHT,
    VFX_RENDER_QUALITY,
    VFX_SELECTOR_ENABLED,
    VFX_SELECTOR_HINT_WEIGHT,
    VFX_SELECTOR_TOP,
    VFX_SLOT_MACROS,
    VFX_SLOT_MACRO_LIBRARY,
    _vfx_event_group,
    _vfx_expand_recipe_macros,
    _vfx_find_recipe,
    _vfx_infer_channel,
    _vfx_infer_lane,
    _vfx_lint_recipe,
    _vfx_manifest_from_recipe,
    _vfx_parent_effect_profile,
    _vfx_particle_address_catalog,
    _vfx_resolve_particle_system_id,
    _vfx_slot_score,
    _vfx_timeline_from_manifest,
    attach_hybrid_vfx_manifest,
    compact_vfx_macro_card,
    compact_vfx_recipe_card,
    get_vfx_recipes,
    vfx_director_name_bank,
    vfx_manifest_effect_stack,
)
from infini_local.core.contract_versions import (
    TMODLOADER_GREY_ZONE_NOTES,
    build_contract_versions,
)
from infini_local.core.runtime_authoring import (
    ENGINE_FN_CATALOG_V2,
    ENGINE_RUNTIME_API_VERSION,
    compile_runtime_plan_to_genome_result,
    compile_runtime_plan_to_genome_patch,
    compiled_runtime_contract,
    infer_attack_pattern_from_runtime,
    normalize_runtime_plan_inplace,
    structural_repair_runtime_plan_inplace,
    runtime_plan_provenance_report,
    runtime_plan_quality_report,
    runtime_plan_validation_report,
    runtime_plan,
    find_call,
    all_calls,
)
from infini_local.core.llm_json_tools import (
    extract_json,
    json_object_candidates,
    parse_first_valid_llm_json,
)
from infini_local.storage import world_storage
from infini_local.services import sdcpp_backend
from infini_local.services import sdcpp_service
from infini_local.storage import failure_state
from infini_local.services import asset_sync_service
from infini_local.services import combine_endpoint
from infini_local.web import trace_dashboard
from infini_local.web.vfx_debug_routes import VfxDebugRoutes
from infini_local.web.server_utility_routes import ServerUtilityRoutes
from infini_local.services import visual_asset_pipeline
from infini_local.services import network_info_service
from infini_local.services.visual_asset_pipeline import (
    compact_zimage_asset_prompt,
    sanitize_image_prompt_background,
    sanitize_projectile_prompt_multiplicity,
    sanitize_visual_palette,
    sprite_status_from_raw_path,
    strip_conflicting_sprite_prompt_bits,
    visual_palette_entry_is_chroma_key_noise as _visual_palette_entry_is_chroma_key_noise,
    zimage_palette_sentence,
    zimage_pe_clean_text,
    zimage_text_policy_sentence,
)
from infini_local.core.item_identity_tools import (
    name_of,
    slug,
    stable_hash,
    item_identity,
    generated_data_of,
    fingerprint_of,
    item_field,
    item_num,
    item_bool,
    recipe_key as _world_recipe_key,
)


# =============================================================================
# NAV: PIPELINE_SUPPORT_EXTRACTED_FROM_SERVER
# =============================================================================

def _multiplayer_connect_info() -> dict[str, Any]:
    return network_info_service.multiplayer_connect_info(
        local_generator_port=env_int("INFINI_PORT", 5055, lo=1, hi=65535),
        terraria_port=TERRARIA_PORT,
        asset_public_base_url=ASSET_PUBLIC_BASE_URL,
        host=env_str("INFINI_HOST", "127.0.0.1"),
    )


USE_LLM = env_bool("INFINI_USE_LLM", False)
# The LLM authors engine-facing parameters and runtime calls;
# Python validates ranges and translates them to explicit C# AttackSpec fields.
# Deterministic fallback/self-test paths are kept isolated from the authored runtime.
LLM_RUNTIME_AUTHORING = env_bool("INFINI_LLM_RUNTIME_AUTHORING", True)
LLM_RUNTIME_PLAN_REQUIRED = env_bool("INFINI_LLM_RUNTIME_PLAN_REQUIRED", True)
LLM_RUNTIME_STRICT_VALIDATION = env_bool("INFINI_LLM_RUNTIME_STRICT_VALIDATION", True)
LLM_RUNTIME_MAX_CONCEPT_CANDIDATES = env_int("INFINI_LLM_RUNTIME_MAX_CONCEPT_CANDIDATES", 5, lo=1, hi=16)
ALLOW_DETERMINISTIC_DEV_FALLBACK = env_bool("INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK", False)
# LLM provider selection. Local LM Studio/Ollama remains the default, but v0.4.49
# can also use OpenRouter or any OpenAI-compatible remote API.
LLM_PROVIDER = env_str("INFINI_LLM_PROVIDER", "").lower()  # local, openrouter, openai_compat
LMSTUDIO_URL = env_first(("INFINI_LMSTUDIO_URL", "OPENAI_BASE_URL"), "http://127.0.0.1:1234").rstrip("/")
LMSTUDIO_MODEL = env_first(("INFINI_LMSTUDIO_MODEL", "OPENAI_MODEL"), "auto")
OPENROUTER_BASE_URL = env_str("INFINI_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_API_KEY = env_first(("INFINI_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"), "")
OPENROUTER_MODEL = env_first(("INFINI_OPENROUTER_MODEL", "OPENROUTER_MODEL"), "auto")
OPENROUTER_HTTP_REFERER = env_str("INFINI_OPENROUTER_HTTP_REFERER", "https://github.com/InfiniCrafterLocal")
OPENROUTER_APP_TITLE = env_str("INFINI_OPENROUTER_APP_TITLE", "InfiniCrafterLocal")
OPENAI_COMPAT_BASE_URL = env_first(("INFINI_OPENAI_COMPAT_BASE_URL", "OPENAI_BASE_URL"), "").rstrip("/")
OPENAI_COMPAT_API_KEY = env_first(("INFINI_OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"), "")
OPENAI_COMPAT_MODEL = env_first(("INFINI_OPENAI_COMPAT_MODEL", "OPENAI_MODEL"), "auto")
LLM_FALLBACK_PROVIDER = env_str("INFINI_LLM_FALLBACK_PROVIDER", "").lower()
LLM_FALLBACK_MODEL = env_str("INFINI_LLM_FALLBACK_MODEL", "")
LLM_FALLBACK_BASE_URL = env_str("INFINI_LLM_FALLBACK_BASE_URL", "").rstrip("/")
LLM_FALLBACK_API_KEY = env_str("INFINI_LLM_FALLBACK_API_KEY", "")
LLM_FALLBACK_NETWORK_FAILS = env_int("INFINI_LLM_FALLBACK_NETWORK_FAILS", 2, lo=1, hi=10)
LLM_RESPONSE_FORMAT_MODE = env_str("INFINI_LLM_RESPONSE_FORMAT", "auto").lower()  # auto, json_schema, json_object, off
# LLM output/reasoning control. OpenRouter supports a unified `reasoning` object;
# local OpenAI-compatible servers usually do not, so local reasoning is prompt-hint only.
LLM_MAX_TOKENS = env_int("INFINI_LLM_MAX_TOKENS", 9000, lo=256, hi=64000)
LLM_REASONING_MODE = env_str("INFINI_LLM_REASONING_MODE", "off").lower()
LLM_REASONING_MAX_TOKENS = env_int("INFINI_LLM_REASONING_MAX_TOKENS", 1500, lo=0, hi=32000)
LLM_REASONING_EXCLUDE = env_bool("INFINI_LLM_REASONING_EXCLUDE", True)
LLM_LOCAL_REASONING_PROMPT = env_bool("INFINI_LLM_LOCAL_REASONING_PROMPT", True)
_RESOLVED_LLM_MODEL: str | None = None

# Visual/image backend configuration lives in pipeline_visual_config.py; this
# module re-exports it for the legacy pipeline_support import surface.
from infini_local.pipelines.pipeline_visual_config import (
    IMAGE_BACKEND,
    A1111_URL,
    COMFYUI_URL,
    SDCPP_MODEL,
    SDCPP_VAE,
    SDCPP_LLM,
    SDCPP_LORA_DIR,
    SDCPP_LORA_FILE,
    SDCPP_LORA_WEIGHT,
    SDCPP_LORA_PROMPT_TAGS,
    SDCPP_WIDTH,
    SDCPP_HEIGHT,
    SDCPP_STEPS,
    SDCPP_CFG,
    SDCPP_SAMPLER,
    SDCPP_SEED,
    ZIMAGE_PROMPT_CONTRACT,
    ZIMAGE_POSITIVE_ONLY,
    SDCPP_SERVER_URL,
    SDCPP_SERVER_HOST,
    SDCPP_SERVER_PORT,
    SDCPP_SERVER_AUTOSTART,
    SDCPP_SERVER_EXE,
    SDCPP_DEFAULT_COMMAND_TEMPLATE,
    SDCPP_SERVER_COMMAND_MODE,
    SDCPP_SERVER_COMMAND_TEMPLATE,
    SDCPP_SERVER_EXTRA_ARGS,
    SDCPP_MODE,
    SDCPP_TIMEOUT,
    SDCPP_SERVER_HEALTH_PATHS,
    SDCPP_SERVER_TXT2IMG_PATHS,
    SDCPP_SERVER_PAYLOAD_STYLE,
    SDCPP_SERVER_STARTUP_TIMEOUT,
    SDCPP_SERVER_REQUEST_TIMEOUT,
    SDCPP_SERVER_SHOW_CONSOLE,
    SDCPP_SERVER_LOG_FILE,
    SDCPP_SERVER_STATE,
    _sdcpp_config,
    LAST_COMBINE_FAILURE,
    LAST_COMBINE_FAILURE_FILE,
    cleanup_sdcpp_server_process,
    _install_sdcpp_cleanup_handlers,
    COMFYUI_WORKFLOW,
    COMFYUI_WORKFLOW_LORA,
    COMFYUI_WORKFLOW_NO_LORA,
    COMFYUI_CHECKPOINT,
    COMFYUI_LORA_NAME,
    COMFYUI_LORA_WEIGHT,
    COMFYUI_TRIGGER,
    COMFYUI_WIDTH,
    COMFYUI_HEIGHT,
    COMFYUI_STEPS,
    COMFYUI_CFG,
    COMFYUI_SAMPLER,
    COMFYUI_SCHEDULER,
    COMFYUI_DENOISE,
    COMFYUI_TIMEOUT,
    COMFYUI_POLL_INTERVAL,
    COMFYUI_CLIENT_ID,
    IMAGE_API_BASE_URL,
    IMAGE_API_KEY,
    IMAGE_API_MODEL,
    IMAGE_API_PATH,
    IMAGE_API_SIZE,
    IMAGE_API_TIMEOUT,
    IMAGE_API_EXTRA_HEADERS_JSON,
    GENERATE_VARIANTS,
    VISUAL_ASSET_MODE,
    VISUAL_GENERATE_CHILD_FIELD_IMAGES,
    VISUAL_GENERATE_IMPACT_IMAGES,
    VISUAL_GENERATE_PROJECTILE_IMAGES,
    PATTERN_LIBRARY_CARDS,
    PATTERN_REPAIR_ATTEMPTS,
    PATTERN_REPAIR_TIMEOUT,
    VISUAL_DIRECTOR_LLM,
    VISUAL_PIPELINE_PROFILE,
    contract_versions_payload,
    VISUAL_GENERATION_TIMEOUT,
    PROJECTILE_SPRITE_CANVAS,
    IMPACT_SPRITE_CANVAS,
    CHILD_SPRITE_CANVAS,
    FIELD_SPRITE_CANVAS,
    REMOVE_BG,
    BG_REMOVE_MODE,
    BG_COLOR,
    REQUIRE_PILLOW,
    CHROMA_TOLERANCE,
    ALPHA_THRESHOLD,
    SPRITE_KEYER_SPILL_RADIUS,
    SPRITE_KEYER_RESIDUE_STEPS,
    SPRITE_PADDING,
    SAVE_SPRITE_STAGES,
    PIXEL_POSTERIZE,
    MAX_COLORS,
    SPRITE_PROCESSING_PROFILE,
    SPRITE_MASTER_CANVAS,
    SPRITE_DOWNSCALE_FILTER,
    SPRITE_CHROMA_DEFRINGE,
    SPRITE_PREMULTIPLIED_RESIZE,
    DENOISE_STRAY_PIXELS,
    SPRITE_RETRIES,
    SPRITE_MIN_BBOX_RATIO,
    SPRITE_MAX_BBOX_RATIO,
    SPRITE_ITEM_CORE_ALPHA_THRESHOLD,
    SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
    ITEM_ICON_TARGET_FILL,
    PROJECTILE_ICON_TARGET_FILL,
    IMPACT_ICON_TARGET_FILL,
    CHILD_ICON_TARGET_FILL,
    FIELD_ICON_TARGET_FILL,
    VISUAL_STRICT_AI_AUTHORSHIP,
    VISUAL_ALLOW_PROCEDURAL_FALLBACK,
    VISUAL_REQUIRE_ITEM_SPRITE,
    VISUAL_REQUIRE_ZIMAGE_BACKEND,
    SPRITE_MIN_OPAQUE_PCT,
    SPRITE_MAX_OPAQUE_PCT,
    SPRITE_MAX_EDGE_TOUCH_PCT,
    A1111_LORA_NAME,
    A1111_LORA_WEIGHT,
    A1111_TRIGGER,
    A1111_WIDTH,
    A1111_HEIGHT,
    A1111_BATCH_SIZE,
)

LAST_COMBINE_FAILURE: dict[str, Any] = {}
LAST_COMBINE_FAILURE_FILE = CACHE_DIR / "last_combine_failure.json"

from infini_local.storage.trace_runtime import (
    PROMPT_TRACE_FILE,
    TRACE_EVENTS_TAIL,
    TRACE_FILE,
    TRACE_MAX_PROMPT_CHARS,
    TRACE_PROMPTS_ENABLED,
    _json_slim,
    _tail_ndjson,
    _tail_text_file,
    _trace_clip,
    _trace_message_summary,
    log_event,
    trace_event,
)

def _env_float(name: str, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return env_float(name, default, lo=lo, hi=hi)

# Item power/knowledge helpers live in item_power_knowledge.py; pipeline_support
# re-exports them for the legacy public import path.
from infini_local.pipelines.item_power_knowledge import (
    CATEGORY_CREATIVITY,
    CATEGORY_ENFORCE_SAMPLED,
    CATEGORY_SALT,
    ITEM_KNOWLEDGE,
    ITEM_KNOWLEDGE_PATH,
    KNOWLEDGE_ENABLED,
    MATERIAL_RARITY_MULT,
    MODDED_HIGH_TIERS,
    MODDED_RARITY_COLOR_HINTS,
    MODDED_RARITY_LADDER,
    RARITY_BASELINE_ENABLED,
    RARITY_BASELINE_STRENGTH,
    RARITY_BASELINE_TABLE,
    RECURSIVE_POWER_GROWTH,
    TIER_DEFAULT_POWER,
    TIER_RANK,
    UNIVERSAL_RECIPE_MODE,
    VANILLA_ENDGAME_POWER,
    apply_item_knowledge,
    build_item_knowledge,
    canonicalize,
    fingerprint_tags,
    generation_depth,
    generic_modded_progression_signal,
    guess_head,
    infer_item_card,
    is_currency_ammo_item,
    is_low_tier_consumable_projectile_item,
    is_material_parent,
    is_simple_low_tier_melee_weapon,
    item_knowledge_power,
    known_item_entry,
    load_item_knowledge,
    lower_name,
    material_catalyst_pressure,
    mechanic_signal_power,
    modded_rarity_entry,
    pair_catalyst_pressure,
    rarity_baseline_signal,
    rarity_details_of,
    rarity_role_weight,
    rarity_tier_estimate,
    recipe_coherence,
    recipe_meta,
    runtime_recipe_frame_for_entry,
    stat_signal_power,
    tags_of,
)


# =============================================================================
# NAV: RUNTIME_DUMPS_AND_ITEM_LOOKUP
# =============================================================================
# Runtime dump loading and lookup live in pipeline_runtime_dumps.py; this module
# re-exports the legacy names for callers that still import pipeline_support.
from infini_local.pipelines.pipeline_runtime_dumps import (
    ITEMS_RUNTIME_DUMP_PATH,
    PROJECTILES_RUNTIME_DUMP_PATH,
    RUNTIME_ITEMS,
    RUNTIME_ITEMS_BY_NAME,
    RUNTIME_ITEMS_BY_TYPE,
    RUNTIME_PROJECTILES,
    RUNTIME_PROJECTILES_BY_NAME,
    RUNTIME_PROJECTILES_BY_TYPE,
    _resolve_runtime_dump_path,
    _runtime_dump_candidates,
    load_jsonl_index,
    runtime_item_lookup,
    runtime_projectile_lookup,
)


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

from infini_local.storage.world_recipe_runtime import (
    WorldScopeMissing,
    _delivery_safe_debug,
    atomic_write_json,
    cache_get,
    cache_put,
    is_deliverable_recipe_payload,
    normalize_world_id_from_payload,
    read_json_file,
    read_world_recipe_cache,
    recipe_key,
    safe_file_part,
    sanitize_recipe_for_delivery,
    strip_runtime_only_fields,
    update_world_recipe_index,
    world_recipe_dir,
    world_recipe_file,
    write_world_manifest,
    write_world_recipe_cache,
)


# =============================================================================
# NAV: WORLD_CACHE_AND_STORAGE
# =============================================================================


def trace_snapshot() -> dict[str, Any]:
    failure: Any = last_combine_failure_summary()
    try:
        if LAST_COMBINE_FAILURE_FILE.exists():
            failure = json.loads(LAST_COMBINE_FAILURE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    provider = active_llm_provider()
    return {
        "ok": True,
        "version": APP_VERSION,
        "time": int(time.time()),
        "serverRoot": str(ROOT),
        "configPath": str(CONFIG_PATH),
        "pid": os.getpid(),
        "cacheDir": str(CACHE_DIR),
        "traceConfig": {
            "tracePrompts": TRACE_PROMPTS_ENABLED,
            "maxPromptChars": TRACE_MAX_PROMPT_CHARS,
            "eventsTail": TRACE_EVENTS_TAIL,
            "promptTraceFile": str(PROMPT_TRACE_FILE),
            "pipelineTraceFile": str(TRACE_FILE),
            "eventsFile": str(CACHE_DIR / "events.ndjson"),
        },
        "pipeline": {
            "useLLM": USE_LLM,
            "llmProvider": provider,
            "llmModel": (OPENROUTER_MODEL if provider == "openrouter" else OPENAI_COMPAT_MODEL if provider == "openai_compat" else LMSTUDIO_MODEL),
            "llmAuth": llm_auth_snapshot(),
            "llmRuntimeAuthoring": LLM_RUNTIME_AUTHORING,
            "llmRuntimePlanRequired": LLM_RUNTIME_PLAN_REQUIRED,
            "imageBackend": IMAGE_BACKEND,
            "visualAssetMode": VISUAL_ASSET_MODE,
            "visualDirectorLLM": VISUAL_DIRECTOR_LLM,
            "vfxLlmDirector": VFX_LLM_DIRECTOR_ENABLED,
            "recipeIdentityVersion": RECIPE_IDENTITY_VERSION,
            "contractVersions": contract_versions_payload(),
            "worldRecipesDir": str(WORLD_RECIPES_DIR),
        },
        "sdcpp": sdcpp_debug_snapshot(include_log_tail=True),
        "lastCombineFailure": failure,
        "events": _tail_ndjson(CACHE_DIR / "events.ndjson", TRACE_EVENTS_TAIL),
        "pipelineTrace": _tail_ndjson(TRACE_FILE, TRACE_EVENTS_TAIL),
        "promptTrace": _tail_ndjson(PROMPT_TRACE_FILE, min(TRACE_EVENTS_TAIL, 80)),
    }


def trace_snapshot_html() -> str:
    return trace_dashboard.render_trace_snapshot_html(
        trace_snapshot(),
        app_version=APP_VERSION,
        trace_clip=_trace_clip,
    )


# -----------------------------------------------------------------------------
# Canonicalization
# -----------------------------------------------------------------------------


# Pure runtime/prompt constants live in pipeline_runtime_constants.py; this
# module re-exports them for the legacy pipeline_support import surface.


class PlannerUnavailable(RuntimeError):
    """Raised when no authored LLM result is available for a real craft."""


from infini_local.pipelines.pipeline_runtime_constants import (
    PALETTES,
    BAD_NAME_PATTERNS,
    EFFECT_PRESENTATION,
    LLM_RAW_TOKEN_MODE,
    LLM_AMMO_REP_LIMIT,
    LLM_INCLUDE_AISTYLE_RAW,
    LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST,
    LLM_ITEM_RAW_KEYS,
    LLM_PROJECTILE_RAW_KEYS,
    LLM_AMMO_ITEM_KEYS,
    STAGE_PROFILES,
    MOVEMENT_CODE,
    MOVEMENT_ALIASES,
    DELIVERY_VALUES,
    RUNTIME_FAMILY_VALUES,
    DELIVERY_ALIASES,
    EFFECT_ALIASES,
    ONHIT_ALIASES,
    EFFECT_CODE,
    ONHIT_CODE,
    LLM_REQUIRED_GENOME_FIELDS,
    LLM_OPTIONAL_GENOME_DEFAULTS,
    LLM_NUMERIC_GENOME_LIMITS,
)
from infini_local.pipelines.engine_pressure_metrics import (
    behavior_cost_multiplier,
    clamp_float,
    dict_get_ci,
    estimate_engine_metrics,
    sanitize_genome_engine,
)

# -----------------------------------------------------------------------------
# Sprite generation / judge / postprocess
# -----------------------------------------------------------------------------


# =============================================================================
# NAV: VISUAL_ASSET_PIPELINE
# =============================================================================


# =============================================================================
# NAV: VFX_MANIFEST_PIPELINE
# =============================================================================
# See LocalGenerator/vfx_manifest.py. server.py imports the frozen generation-time VFX manifest pipeline.


# =============================================================================
# NAV: FINAL_NORMALIZE_AND_HTTP
# =============================================================================

from infini_local.pipelines.generated_parent_summary import (
    attach_generated_parent_summary,
    generated_parent_summary_from_data,
)

def final_normalize(data: dict[str, Any]) -> dict[str, Any]:
    data.pop("_llmContinuation", None)
    data.pop("_runtimePlanCompileCache", None)
    data.setdefault("schemaVersion", 1)
    # Runtime API/engine-call contract version is intentionally separate from the
    # project build version. C# can reject future unsupported executable contracts
    # instead of silently losing behavior.
    data.setdefault("runtimeApiVersion", ENGINE_RUNTIME_API_VERSION)
    data["category"] = normalize_category(data.get("category", "generic"))
    data.setdefault("gameplay", {}).setdefault("kind", data["category"])
    data["gameplay"]["kind"] = normalize_category(data["gameplay"].get("kind"))
    data.setdefault("accessory", {}).setdefault("enabled", data["category"] == "accessory")
    if data["category"] == "accessory":
        data.setdefault("attack", {})["enabled"] = False
        data["gameplay"]["kind"] = "accessory"
    data.setdefault("itemKnowledge", {})
    visual = data.setdefault("visual", {})
    if isinstance(visual.get("palette"), list):
        visual["palette"] = [str(x) for x in visual.get("palette", []) if str(x).strip()][:8]
    attack = data.setdefault("attack", {})
    if isinstance(attack, dict) and attack.get("genome") is None:
        attack["genome"] = {}
    if not isinstance(data.get("presentationGenome"), dict) or not data.get("presentationGenome"):
        data["presentationGenome"] = presentation_from_genome(data)
    if not isinstance(data.get("soundProfile"), dict) or not data.get("soundProfile"):
        data["soundProfile"] = sound_profile_from_genome(data)
    if isinstance(data["itemKnowledge"], dict) and "resultCard" not in data["itemKnowledge"]:
        data["itemKnowledge"]["resultCard"] = build_result_item_card(data, {}, {})
    parent_a_for_name = {"name": data.get("parentA", "")}
    parent_b_for_name = {"name": data.get("parentB", "")}
    if bad_result_name(data.get("name"), parent_a_for_name, parent_b_for_name):
        raise PlannerUnavailable("final result name is invalid after validation; craft failed and ingredients must be refunded")
    data.setdefault("debug", {})
    data["debug"].setdefault("generator", "InfiniCrafterLocal")
    data["debug"].setdefault("version", APP_VERSION)
    # C# JsonSerializer uses PascalCase properties but is case-insensitive; camelCase is fine.
    return data

# -----------------------------------------------------------------------------
# HTTP server
# -----------------------------------------------------------------------------

# =============================================================================
# Legacy compatibility re-exports
# =============================================================================
# New code should import these symbols from their owner modules directly; this
# block keeps older pipeline_support callers working without making it a design owner.
from infini_local.pipelines.parent_context_pipeline import (
    projectile_behavior_tags,
    source_weapon_profile,
)
from infini_local.pipelines.result_identity_policy import (
    bad_result_name,
    normalize_category,
    parent_primary_category,
)
from infini_local.pipelines.result_knowledge_card import (
    build_result_item_card,
)
from infini_local.pipelines.presentation_sound import (
    presentation_from_genome,
    sound_profile_from_genome,
)
from infini_local.pipelines.visual_prompt_contracts import (
    compact_visual_words,
)
