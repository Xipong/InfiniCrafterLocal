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
from infini_local.core.runtime_effect_policy import onhit_uses_burst_dust_feedback
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
from infini_local.storage import trace_tools
from infini_local.services import sdcpp_backend
from infini_local.services import sdcpp_service
from infini_local.storage import failure_state
from infini_local.services import asset_sync_service
from infini_local.services import combine_endpoint
from infini_local.services import runtime_dump_service
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

from infini_local.pipelines import (
    combine_pipeline,
    llm_authoring_pipeline,
    parent_context_pipeline,
    visual_generation_pipeline,
    image_backend_pipeline,
    sprite_processing_pipeline,
)
from infini_local.pipelines.combine_pipeline import (
    record_combine_failure,
    clear_combine_failure,
    last_combine_failure_summary,
    combine_cache_lookup,
    combine,
    deterministic_plan,
    clean_name,
    theme_word,
    title_words,
    bad_result_name,
    choose_from,
    name_noun_for,
    name_prefixes_for,
    creative_result_name,
    repair_name_if_needed,
    try_llm_name_repair,
    normalize_category,
    parent_primary_category,
    is_weapon_like_parent,
    _weighted_choice,
    _policy_seed,
    category_policy,
    choose_result_category,
    coerce_category_by_policy,
    canonical_for_result,
    rep,
    rep_for_parent,
    inh_for_parent,
    required_anchors_from,
    required_anchors_from_tags,
    palette_from,
    apply_family_locks_to_genome,
    _stringish,
    validate_and_repair,
    preservation_score,
    item_power_score,
    tier_rank,
    influenced_tier,
    universal_parent_relation,
    recipe_power_transfer,
    stat_profile_for,
    stage_profile_for,
    canvas_tier_for,
    size_profile_for,
    balanced_damage,
    _normalize_authored_enum_value,
    safe_enum,
    proposed_attack_genome,
    combat_genome_required_for,
    genome_defects,
    merge_genome_repair,
    try_llm_genome_repair,
    repair_llm_combat_genome_if_needed,
    is_llm_planner,
    _parse_required_float,
    _hard_clamp_authored_number,
    _require_authored_enum,
    llm_authored_weapon_genome,
    weapon_genome_for,
    normalize_authored_attack_pattern,
    weapon_numbers_from_genome,
    attack_pattern_for,
    accessory_stats_for,
    build_result_item_card,
    attach_result_knowledge_card,
    parent_combo_looks_like_bow,
    projectile_family_text,
    _explicit_visual_family_value,
    infer_projectile_visual_family,
    parent_projectile_family,
    choose_parent_projectile_size_reference,
    apply_parent_projectile_affordance,
    _parent_tool_power,
    _bounded_parent_potion_stats,
    attach_gameplay_and_attack,
    clamp,
    movement_for,
    effect_for,
    onhit_for,
    presentation_from_genome,
    sound_profile_from_genome,
    attach_presentation_and_sound,
)
from infini_local.pipelines.llm_authoring_pipeline import (
    active_llm_provider,
    _join_openai_compat_url,
    llm_base_url,
    llm_chat_completions_url,
    llm_models_url,
    llm_auth_snapshot,
    ensure_llm_auth_configured,
    llm_headers,
    llm_json_response_format,
    normalize_llm_attack_shape,
    normalize_behavior_toy_fields,
    runtime_value,
    runtime_plan_to_attack_genome_patch,
    normalize_runtime_authoring_fields,
    terraria_tick_guide_for_llm,
    _catalog_text,
    sharp_engine_fn_catalog_for_llm,
    concise_terraria_tick_guide_for_llm,
    engine_runtime_capability_contract_for_llm,
    authored_num,
    authored_int,
    authored_weapon_damage,
    authored_str,
    llm_category_without_router,
    llm_runtime_result_kind_policy,
    build_llm_author_payload,
    planner_prompt_usability_report,
    try_llm_plan,
    call_llm_vfx_director,
    llm_answer_max_tokens,
    visual_director_max_tokens,
    llm_reasoning_payload,
    llm_reasoning_system_suffix,
    apply_llm_common_options,
    http_get_json,
    resolve_llm_model,
    _clean_llm_payload,
    http_json,
    _llm_replay_stage_from_payload,
    _replay_content_from_json_object,
    _load_llm_replay_raw,
    _llm_replay_json_response,
    llm_chat_json,
)
from infini_local.pipelines.parent_context_pipeline import (
    _raw_section_dict,
    _raw_section_list,
    _strip_texture_metrics_for_llm,
    projectile_profile_of,
    ammo_profile_of,
    effective_projectile_profile_of,
    proj_num,
    proj_bool,
    projectile_behavior_tags,
    source_weapon_profile,
    parent_weapon_profiles,
    runtime_facts_for_prompt,
    auto_features_for_prompt,
    llm_parent_card,
    _compact_keep,
    _compact_raw_value,
    _select_raw_keys,
    compact_item_raw_for_llm,
    _pnum,
    _pbool,
    projectile_behavior_digest_for_llm,
    compact_projectile_profile,
    compact_ammo_profile,
    _raw_item_fields_for_llm,
    compact_vanilla_flags_for_llm,
    _projectile_profile_same_except_source,
    _dedupe_projectile_profile,
    raw_parent_card_for_llm,
    combined_tags,
    behavior_policy_for_prompt,
)
from infini_local.pipelines.visual_generation_pipeline import (
    attach_visual,
    build_image_prompt,
    maybe_generate_sprite,
    asset_negative_prompt,
    chroma_rgb,
    chroma_name,
    sprite_background_positive_clause,
    sprite_background_negative_clause,
    image_backend_is_zimage,
    zimage_positive_only_enabled,
    zimage_role_description,
    zimage_positive_guard_clause,
    _authored_tether_context,
    authored_tether_like,
    tether_sprite_guard_required,
    _scrub_tether_sprite_body_prompt,
    tether_visual_prompt_guard,
    family_prompt_clause,
    sanitize_projectile_family_prompt,
    zimage_subject_sentence,
    sprite_contract_for,
    role_contract_prompt_clause,
    role_style_prefix,
    normalize_asset_prompt,
    should_generate_child_asset,
    should_generate_field_asset,
    projectile_visual_blob,
    is_tiny_projectile_visual,
    is_melee_arc_projectile_visual,
    effective_projectile_canvas,
    _visual_kit,
    _role_baked_asset_spec,
    _role_asset_prompt,
    _asset_mode_from_value,
    authored_asset_mode,
    legacy_projectile_baked_sprite_fallback,
    build_visual_asset_plan,
    _asset_sha256,
    _asset_descriptor,
    sprite_contract_for_asset,
    _compact_text,
    _parent_manifest_summary,
    _asset_manifest_entry,
    write_visual_manifest,
    compact_visual_words,
    build_projectile_image_prompt,
    build_impact_image_prompt,
    build_child_image_prompt,
    build_field_image_prompt,
    apply_visual_director,
    generate_visual_asset,
    maybe_generate_visual_assets,
    VisualDeliveryBlocked,
)
from infini_local.pipelines.image_backend_pipeline import (
    http_binary_get,
    json_deep_replace,
    resolve_comfyui_workflow_path,
    comfyui_mapping,
    poll_comfyui_history,
    extract_comfyui_images,
    fetch_comfyui_image,
    sdcpp_repair_command_template,
    sdcpp_command_mode_is_template,
    sdcpp_base_arg_list,
    quote_cmd_arg,
    _extra_has_flag,
    sdcpp_effective_extra_args,
    sdcpp_effective_extra_arg_list,
    sdcpp_server_is_configured,
    http_json_get,
    sdcpp_server_is_alive,
    build_sdcpp_server_command,
    _stringify_cmd,
    sdcpp_debug_snapshot,
    ensure_sdcpp_server,
    sdcpp_server_payload,
    extract_image_from_server_response,
    generate_sdcpp_server,
    image_api_headers,
    image_api_url,
    extract_image_from_api_response,
    generate_image_api,
    generate_sdcpp,
    append_a1111_lora,
    generate_a1111,
    generate_comfyui,
)
from infini_local.pipelines.sprite_processing_pipeline import (
    alpha_bbox_threshold,
    bbox_union,
    bbox_expand,
    bbox_dims,
    bbox_center,
    sprite_bbox_stats,
    pick_best_sprite,
    save_stage,
    color_distance,
    chroma_like_rgb,
    magenta_key_pixel_ratio,
    dilate_mask,
    cleanup_alpha_soft,
    is_neutral_or_white_foreground_rgb,
    is_dark_key_residue_rgb,
    median_int,
    percentile,
    border_sample_pixels,
    estimate_sprite_key_profile,
    magic_wand_bg_candidate_rgb,
    local_edge_contrast,
    floodfill_keylike_background,
    grow_background_through_key_residue,
    remove_key_colored_holes,
    _poster_card_like_rgb,
    _quant_bucket,
    remove_inner_poster_card_background,
    find_nearby_clean_foreground_color,
    close_tiny_background_cracks,
    remove_background_sprite_keyer,
    apply_background_removal,
    cleanup_alpha,
    denoise_alpha_singletons,
    scrub_transparent_rgb,
    defringe_chroma_edges,
    neutralize_chroma_edge_colors,
    sprite_resample_filter,
    resize_rgba_premultiplied,
    prepare_sprite_master,
    bake_sprite_from_master,
    alpha_stats,
    fit_to_canvas,
    palette_cleanup,
    edge_touch_ratio,
    validate_processed_sprite,
    sprite_validation_fatal,
    validation_retry_notes,
    build_retry_prompt_from_validation,
    strengthen_prompt_for_retry,
    postprocess_sprite,
)


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
LLM_RESPONSE_FORMAT_MODE = env_str("INFINI_LLM_RESPONSE_FORMAT", "auto").lower()  # auto, json_schema, json_object, off
# LLM output/reasoning control. OpenRouter supports a unified `reasoning` object;
# local OpenAI-compatible servers usually do not, so local reasoning is prompt-hint only.
LLM_MAX_TOKENS = env_int("INFINI_LLM_MAX_TOKENS", 9000, lo=256, hi=64000)
LLM_REASONING_MODE = env_str("INFINI_LLM_REASONING_MODE", "off").lower()
LLM_REASONING_MAX_TOKENS = env_int("INFINI_LLM_REASONING_MAX_TOKENS", 1500, lo=0, hi=32000)
LLM_REASONING_EXCLUDE = env_bool("INFINI_LLM_REASONING_EXCLUDE", True)
LLM_LOCAL_REASONING_PROMPT = env_bool("INFINI_LLM_LOCAL_REASONING_PROMPT", True)

IMAGE_BACKEND = env_str("INFINI_IMAGE_BACKEND", "procedural").lower()  # procedural, a1111, comfyui, sdcpp, off
A1111_URL = env_str("INFINI_A1111_URL", "http://127.0.0.1:7860").rstrip("/")
COMFYUI_URL = env_str("INFINI_COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
# stable-diffusion.cpp backend. v0.4.19 removes per-image CLI generation entirely.
# Only persistent sd-server/http mode is supported for gameplay. The model must stay hot in memory.
SDCPP_MODEL = env_first(("INFINI_SDCPP_MODEL", "SDCPP_MODEL"), "")
# Z-Image needs separate text encoder/LLM and VAE/AE files in stable-diffusion.cpp.
# Keep them as dedicated fields so users do not have to hand-type fragile extra args.
SDCPP_VAE = env_str("INFINI_SDCPP_VAE", "")
SDCPP_LLM = env_str("INFINI_SDCPP_LLM", "")
SDCPP_LORA_DIR = env_str("INFINI_SDCPP_LORA_DIR", "")
SDCPP_LORA_FILE = env_str("INFINI_SDCPP_LORA_FILE", "")
SDCPP_LORA_WEIGHT = env_str("INFINI_SDCPP_LORA_WEIGHT", "0.65") or "0.65"
SDCPP_LORA_PROMPT_TAGS = env_str("INFINI_SDCPP_LORA_PROMPT_TAGS", "")
if SDCPP_LORA_FILE:
    _lora_path = Path(SDCPP_LORA_FILE)
    # A concrete LoRA file should drive the directory passed to sd.cpp. This avoids
    # stale GUI defaults such as C:\Games\sdcpp\loras pointing at the wrong folder.
    _file_lora_dir = sdcpp_backend.lora_dir_from_file(SDCPP_LORA_FILE)
    if _file_lora_dir:
        SDCPP_LORA_DIR = _file_lora_dir
    if not SDCPP_LORA_PROMPT_TAGS and _lora_path.stem:
        SDCPP_LORA_PROMPT_TAGS = sdcpp_backend.lora_tag_from_file(SDCPP_LORA_FILE, SDCPP_LORA_WEIGHT)
SDCPP_WIDTH = env_int("INFINI_SDCPP_WIDTH", 512)
SDCPP_HEIGHT = env_int("INFINI_SDCPP_HEIGHT", SDCPP_WIDTH, lo=64, hi=2048)
SDCPP_STEPS = env_int("INFINI_SDCPP_STEPS", 8)
SDCPP_CFG = env_float("INFINI_SDCPP_CFG", 1.0)
SDCPP_SAMPLER = env_str("INFINI_SDCPP_SAMPLER", "euler")
SDCPP_SEED = env_int("INFINI_SDCPP_SEED", -1)
ZIMAGE_PROMPT_CONTRACT = env_str("INFINI_ZIMAGE_PROMPT_CONTRACT", "auto").lower()  # auto, 1, 0
ZIMAGE_POSITIVE_ONLY = env_bool("INFINI_ZIMAGE_POSITIVE_ONLY", True)
SDCPP_SERVER_URL = env_str("INFINI_SDCPP_SERVER_URL", "http://127.0.0.1:7861").rstrip("/")
SDCPP_SERVER_HOST = env_str("INFINI_SDCPP_SERVER_HOST", "127.0.0.1")
SDCPP_SERVER_PORT = env_int("INFINI_SDCPP_SERVER_PORT", 7861)
SDCPP_SERVER_AUTOSTART = env_bool("INFINI_SDCPP_SERVER_AUTOSTART", False)
SDCPP_SERVER_EXE = env_str("INFINI_SDCPP_SERVER_EXE", "")
SDCPP_DEFAULT_COMMAND_TEMPLATE = "{exe} --diffusion-model {model} -l {host} --listen-port {port} -W {width} -H {height} --steps {steps} --cfg-scale {cfg} --sampling-method {sampler} {extra}"
SDCPP_SERVER_COMMAND_MODE = env_str("INFINI_SDCPP_SERVER_COMMAND_MODE", "safe_args").lower()  # safe_args, template
SDCPP_SERVER_COMMAND_TEMPLATE = env_str("INFINI_SDCPP_SERVER_COMMAND_TEMPLATE", "")
SDCPP_SERVER_EXTRA_ARGS = env_str("INFINI_SDCPP_SERVER_EXTRA_ARGS", "")
SDCPP_MODE = "server"
SDCPP_TIMEOUT = env_int("INFINI_SDCPP_TIMEOUT", env_int("INFINI_VISUAL_GENERATION_TIMEOUT", 240, lo=1, hi=3600), lo=1, hi=3600)
SDCPP_SERVER_HEALTH_PATHS = [x.strip() for x in env_str("INFINI_SDCPP_SERVER_HEALTH_PATHS", "/,/health,/sdapi/v1/sd-models").split(",") if x.strip()]
SDCPP_SERVER_TXT2IMG_PATHS = [x.strip() for x in env_str("INFINI_SDCPP_SERVER_TXT2IMG_PATHS", "/sdapi/v1/txt2img,/txt2img,/generate").split(",") if x.strip()]
SDCPP_SERVER_PAYLOAD_STYLE = env_str("INFINI_SDCPP_SERVER_PAYLOAD_STYLE", "auto").lower()  # auto, a1111, sdcpp, openai
SDCPP_SERVER_STARTUP_TIMEOUT = env_int("INFINI_SDCPP_SERVER_STARTUP_TIMEOUT", 180)
SDCPP_SERVER_REQUEST_TIMEOUT = env_int("INFINI_SDCPP_SERVER_REQUEST_TIMEOUT", SDCPP_TIMEOUT, lo=1, hi=3600)
# v0.4.49: do not hide sd-server output behind PIPE. Z-Image startup bugs need visible logs,
# and verbose sd.cpp output can otherwise fill the pipe and stall the child process.
SDCPP_SERVER_SHOW_CONSOLE = env_bool("INFINI_SDCPP_SERVER_SHOW_CONSOLE", os.name == "nt")
SDCPP_SERVER_LOG_FILE = env_str("INFINI_SDCPP_SERVER_LOG_FILE", str(CACHE_DIR / "sdcpp_server.log"))
SDCPP_SERVER_STATE = sdcpp_service.SdcppServerState()
def _sdcpp_config() -> sdcpp_backend.SdcppBackendConfig:
    return sdcpp_backend.SdcppBackendConfig(
        default_command_template=SDCPP_DEFAULT_COMMAND_TEMPLATE,
        command_mode=SDCPP_SERVER_COMMAND_MODE,
        server_exe=SDCPP_SERVER_EXE,
        model=SDCPP_MODEL,
        vae=SDCPP_VAE,
        llm=SDCPP_LLM,
        lora_dir=SDCPP_LORA_DIR,
        lora_prompt_tags=SDCPP_LORA_PROMPT_TAGS,
        host=SDCPP_SERVER_HOST,
        port=SDCPP_SERVER_PORT,
        width=SDCPP_WIDTH,
        height=SDCPP_HEIGHT,
        steps=SDCPP_STEPS,
        cfg=SDCPP_CFG,
        sampler=SDCPP_SAMPLER,
        extra_args=SDCPP_SERVER_EXTRA_ARGS,
        server_url=SDCPP_SERVER_URL,
        health_paths=SDCPP_SERVER_HEALTH_PATHS,
        zimage_prompt_contract=ZIMAGE_PROMPT_CONTRACT,
        zimage_positive_only=ZIMAGE_POSITIVE_ONLY,
    )


LAST_COMBINE_FAILURE: dict[str, Any] = {}
LAST_COMBINE_FAILURE_FILE = CACHE_DIR / "last_combine_failure.json"

# Rolling black box recorder for GUI/debug: prompts, LLM responses, image prompts,
# sd.cpp startup/image attempts and pipeline steps. This is debug state, not gameplay state.
TRACE_PROMPTS_ENABLED = env_bool("INFINI_TRACE_PROMPTS", True)
TRACE_MAX_PROMPT_CHARS = max(1000, min(120000, env_int("INFINI_TRACE_MAX_PROMPT_CHARS", 18000)))
TRACE_EVENTS_TAIL = max(20, min(500, env_int("INFINI_TRACE_EVENTS_TAIL", 120)))
TRACE_FILE = CACHE_DIR / "pipeline_trace.ndjson"
PROMPT_TRACE_FILE = CACHE_DIR / "prompt_trace.ndjson"


def _json_slim(obj: Any, max_chars: int = 40000) -> Any:
    return trace_tools.json_slim(obj, max_chars)








def cleanup_sdcpp_server_process(reason: str = "cleanup") -> None:
    sdcpp_service.cleanup_server_process(SDCPP_SERVER_STATE, log_event, reason)


def _install_sdcpp_cleanup_handlers() -> None:
    sdcpp_service.install_cleanup_handlers(SDCPP_SERVER_STATE, cleanup_sdcpp_server_process)



_install_sdcpp_cleanup_handlers()
COMFYUI_WORKFLOW = env_str("INFINI_COMFYUI_WORKFLOW", "auto")
COMFYUI_WORKFLOW_LORA = env_str("INFINI_COMFYUI_WORKFLOW_LORA", "")
COMFYUI_WORKFLOW_NO_LORA = env_str("INFINI_COMFYUI_WORKFLOW_NO_LORA", "")
COMFYUI_CHECKPOINT = env_str("INFINI_COMFYUI_CHECKPOINT", "")
COMFYUI_LORA_NAME = env_first(("INFINI_COMFYUI_LORA_NAME", "INFINI_PIXEL_LORA_NAME"), "")
COMFYUI_LORA_WEIGHT = env_first(("INFINI_COMFYUI_LORA_WEIGHT", "INFINI_PIXEL_LORA_WEIGHT"), "0.8")
COMFYUI_TRIGGER = env_first(("INFINI_COMFYUI_TRIGGER", "INFINI_PIXEL_TRIGGER"), "")
COMFYUI_WIDTH = env_int("INFINI_COMFYUI_WIDTH", 512)
COMFYUI_HEIGHT = env_int("INFINI_COMFYUI_HEIGHT", COMFYUI_WIDTH, lo=64, hi=2048)
COMFYUI_STEPS = env_int("INFINI_COMFYUI_STEPS", 16)
COMFYUI_CFG = env_float("INFINI_COMFYUI_CFG", 5.5)
COMFYUI_SAMPLER = env_str("INFINI_COMFYUI_SAMPLER", "euler")
COMFYUI_SCHEDULER = env_str("INFINI_COMFYUI_SCHEDULER", "normal")
COMFYUI_DENOISE = env_float("INFINI_COMFYUI_DENOISE", 1.0)
COMFYUI_TIMEOUT = env_int("INFINI_COMFYUI_TIMEOUT", env_int("INFINI_VISUAL_GENERATION_TIMEOUT", 240, lo=1, hi=3600), lo=1, hi=3600)
COMFYUI_POLL_INTERVAL = env_float("INFINI_COMFYUI_POLL_INTERVAL", 0.75)
COMFYUI_CLIENT_ID = env_str("INFINI_COMFYUI_CLIENT_ID", "infinicrafterlocal")
IMAGE_API_BASE_URL = env_first(("INFINI_IMAGE_API_BASE_URL", "INFINI_OPENAI_COMPAT_IMAGE_BASE_URL"), "https://api.openai.com/v1").rstrip("/")
IMAGE_API_KEY = env_first(("INFINI_IMAGE_API_KEY", "INFINI_OPENAI_COMPAT_IMAGE_API_KEY", "OPENAI_API_KEY"), "")
IMAGE_API_MODEL = env_first(("INFINI_IMAGE_API_MODEL", "INFINI_OPENAI_COMPAT_IMAGE_MODEL"), "gpt-image-1")
IMAGE_API_PATH = env_str("INFINI_IMAGE_API_PATH", "/images/generations")
IMAGE_API_SIZE = env_first(("INFINI_IMAGE_API_SIZE", "INFINI_OPENAI_COMPAT_IMAGE_SIZE"), "512x512")
IMAGE_API_TIMEOUT = env_int("INFINI_IMAGE_API_TIMEOUT", env_int("INFINI_VISUAL_GENERATION_TIMEOUT", 240, lo=1, hi=3600), lo=1, hi=3600)
IMAGE_API_EXTRA_HEADERS_JSON = env_str("INFINI_IMAGE_API_EXTRA_HEADERS_JSON", "")
GENERATE_VARIANTS = env_int("INFINI_IMAGE_VARIANTS", 1)
# Visual asset generation mode. "item" = inventory icon only; "full" = item + projectile + impact briefs.
VISUAL_ASSET_MODE = env_str("INFINI_VISUAL_ASSET_MODE", "full").lower()
VISUAL_GENERATE_CHILD_FIELD_IMAGES = env_bool("INFINI_VISUAL_GENERATE_CHILD_FIELD_IMAGES", False)
VISUAL_GENERATE_IMPACT_IMAGES = env_bool("INFINI_VISUAL_GENERATE_IMPACT_IMAGES", False)
VISUAL_GENERATE_PROJECTILE_IMAGES = env_bool("INFINI_VISUAL_GENERATE_PROJECTILE_IMAGES", True)
# v0.3.15: light pattern library. Do not dump long VFX docs into Gemma.
# The planner sees only a few retrieved pattern cards, and missing/invalid attackPattern
# is repaired by the same LLM in a tiny second call instead of deterministic guessing.
PATTERN_LIBRARY_CARDS = env_int("INFINI_PATTERN_LIBRARY_CARDS", 4)
PATTERN_REPAIR_ATTEMPTS = env_int("INFINI_PATTERN_REPAIR_ATTEMPTS", 0 if LLM_RUNTIME_AUTHORING else 2, lo=0, hi=8)
PATTERN_REPAIR_TIMEOUT = env_int("INFINI_PATTERN_REPAIR_TIMEOUT", 20)
# v0.3.9: merged author-first visual pipeline. Planner writes the toy, visual-director
# builds a role-separated asset pack, generator produces item/projectile/impact/child/field PNGs.
VISUAL_DIRECTOR_LLM = env_bool("INFINI_VISUAL_DIRECTOR_LLM", True)
VISUAL_PIPELINE_PROFILE = env_str("INFINI_VISUAL_PIPELINE_PROFILE", "author_visualpack_v2")


def contract_versions_payload() -> dict[str, Any]:
    return build_contract_versions(
        app_version=APP_VERSION,
        recipe_identity_version=RECIPE_IDENTITY_VERSION,
        runtime_api_version=ENGINE_RUNTIME_API_VERSION,
        visual_pipeline_profile=VISUAL_PIPELINE_PROFILE,
    )
VISUAL_GENERATION_TIMEOUT = env_int("INFINI_VISUAL_GENERATION_TIMEOUT", 240)
PROJECTILE_SPRITE_CANVAS = env_int("INFINI_PROJECTILE_SPRITE_CANVAS", 32)
IMPACT_SPRITE_CANVAS = env_int("INFINI_IMPACT_SPRITE_CANVAS", 32)
CHILD_SPRITE_CANVAS = env_int("INFINI_CHILD_SPRITE_CANVAS", 24)
FIELD_SPRITE_CANVAS = env_int("INFINI_FIELD_SPRITE_CANVAS", 32)
# VFX manifest pipeline constants/functions are imported from vfx_manifest.py after config.env is loaded.
# v0.3.9 one-shot sprite alpha pipeline. Default path:
# 1 generated image per asset -> local alpha removal -> crop/fit/downscale ->
# technical validation -> retry only if PNG is technically broken.
# No VLM judge and no fake best-of-N selection by default.
REMOVE_BG = env_bool("INFINI_REMOVE_BG", True)
BG_REMOVE_MODE = env_str("INFINI_BG_REMOVE_MODE", "sprite_keyer").lower()  # primary supported mode: sprite_keyer
BG_COLOR = env_str("INFINI_BG_COLOR", "magenta").lower()
# v0.4.19: visual generation depends on local alpha/crop/validation; raw SD PNGs are not valid Terraria sprites.
REQUIRE_PILLOW = env_bool("INFINI_REQUIRE_PILLOW", True)
CHROMA_TOLERANCE = env_int("INFINI_CHROMA_TOLERANCE", 34)
ALPHA_THRESHOLD = env_int("INFINI_ALPHA_THRESHOLD", 28)
SPRITE_KEYER_SPILL_RADIUS = env_int("INFINI_SPRITE_KEYER_SPILL_RADIUS", 3)
SPRITE_KEYER_RESIDUE_STEPS = env_int("INFINI_SPRITE_KEYER_RESIDUE_STEPS", 8)
SPRITE_PADDING = env_int("INFINI_SPRITE_PADDING", 2)
SAVE_SPRITE_STAGES = env_bool("INFINI_SAVE_SPRITE_STAGES", False)
PIXEL_POSTERIZE = env_bool("INFINI_PIXEL_POSTERIZE", True)
MAX_COLORS = env_int("INFINI_MAX_COLORS", 32)
# v0.4.55 master-first sprite pipeline.  AI still authors the art; code only performs
# technical image processing: full-res key removal, premultiplied resize, canvas fit,
# palette bake.
SPRITE_PROCESSING_PROFILE = env_str("INFINI_SPRITE_PROCESSING_PROFILE", "master_soft").lower()
SPRITE_MASTER_CANVAS = env_int("INFINI_SPRITE_MASTER_CANVAS", 256, lo=64, hi=2048)
SPRITE_DOWNSCALE_FILTER = env_str("INFINI_SPRITE_DOWNSCALE_FILTER", "box").lower()
SPRITE_CHROMA_DEFRINGE = env_bool("INFINI_SPRITE_CHROMA_DEFRINGE", True)
SPRITE_PREMULTIPLIED_RESIZE = env_bool("INFINI_SPRITE_PREMULTIPLIED_RESIZE", True)
DENOISE_STRAY_PIXELS = env_bool("INFINI_DENOISE_STRAY_PIXELS", False)
SPRITE_RETRIES = env_int("INFINI_SPRITE_RETRIES", 2, lo=0, hi=8)
SPRITE_MIN_BBOX_RATIO = env_float("INFINI_SPRITE_MIN_BBOX_RATIO", 0.10)
SPRITE_MAX_BBOX_RATIO = env_float("INFINI_SPRITE_MAX_BBOX_RATIO", 0.92)
SPRITE_ITEM_CORE_ALPHA_THRESHOLD = env_int("INFINI_SPRITE_ITEM_CORE_ALPHA_THRESHOLD", 56)
SPRITE_EFFECT_CORE_ALPHA_THRESHOLD = env_int("INFINI_SPRITE_EFFECT_CORE_ALPHA_THRESHOLD", 40)
ITEM_ICON_TARGET_FILL = env_float("INFINI_ITEM_ICON_TARGET_FILL", 0.91)
PROJECTILE_ICON_TARGET_FILL = env_float("INFINI_PROJECTILE_ICON_TARGET_FILL", 0.84)
IMPACT_ICON_TARGET_FILL = env_float("INFINI_IMPACT_ICON_TARGET_FILL", 0.82)
CHILD_ICON_TARGET_FILL = env_float("INFINI_CHILD_ICON_TARGET_FILL", 0.72)
FIELD_ICON_TARGET_FILL = env_float("INFINI_FIELD_ICON_TARGET_FILL", 0.86)
VISUAL_STRICT_AI_AUTHORSHIP = env_bool("INFINI_VISUAL_STRICT_AI_AUTHORSHIP", True)
VISUAL_ALLOW_PROCEDURAL_FALLBACK = env_bool("INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK", False)
VISUAL_REQUIRE_ITEM_SPRITE = env_bool("INFINI_VISUAL_REQUIRE_ITEM_SPRITE", True)
VISUAL_REQUIRE_ZIMAGE_BACKEND = env_bool("INFINI_VISUAL_REQUIRE_ZIMAGE_BACKEND", False)
SPRITE_MIN_OPAQUE_PCT = env_float("INFINI_SPRITE_MIN_OPAQUE_PCT", 0.015)
SPRITE_MAX_OPAQUE_PCT = env_float("INFINI_SPRITE_MAX_OPAQUE_PCT", 0.82)
SPRITE_MAX_EDGE_TOUCH_PCT = env_float("INFINI_SPRITE_MAX_EDGE_TOUCH_PCT", 0.12)
A1111_LORA_NAME = env_str("INFINI_A1111_LORA_NAME", "")
A1111_LORA_WEIGHT = env_str("INFINI_A1111_LORA_WEIGHT", "0.8")
A1111_TRIGGER = env_str("INFINI_A1111_TRIGGER", "")
A1111_WIDTH = env_int("INFINI_A1111_WIDTH", 512, lo=64, hi=2048)
A1111_HEIGHT = env_int("INFINI_A1111_HEIGHT", A1111_WIDTH, lo=64, hi=2048)
A1111_BATCH_SIZE = env_int("INFINI_A1111_BATCH_SIZE", 1, lo=1, hi=16)

def _env_float(name: str, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return env_float(name, default, lo=lo, hi=hi)

# 0.0 = almost vanilla/logical, 1.0 = more surprise. The random is deterministic per recipe key.
CATEGORY_CREATIVITY = _env_float("INFINI_CATEGORY_CREATIVITY", 0.38)
# 1 = category is sampled before the LLM and then enforced; 0 = LLM may override within allowed categories.
CATEGORY_ENFORCE_SAMPLED = env_bool("INFINI_CATEGORY_ENFORCE_SAMPLED", False)
CATEGORY_SALT = env_str("INFINI_CATEGORY_SALT", "default")
RECURSIVE_POWER_GROWTH = _env_float("INFINI_RECURSIVE_POWER_GROWTH", 0.035, 0.0, 0.5)
UNIVERSAL_RECIPE_MODE = env_bool("INFINI_UNIVERSAL_RECIPE_MODE", True)
KNOWLEDGE_ENABLED = env_bool("INFINI_KNOWLEDGE_ENABLED", True)
ITEM_KNOWLEDGE_PATH = env_path("INFINI_ITEM_KNOWLEDGE_PATH", DATA_DIR / "item_knowledge.json")

RARITY_BASELINE_ENABLED = env_bool("INFINI_RARITY_BASELINE_ENABLED", True)
RARITY_BASELINE_STRENGTH = _env_float("INFINI_RARITY_BASELINE_STRENGTH", 0.90, 0.0, 1.5)
MATERIAL_RARITY_MULT = _env_float("INFINI_MATERIAL_RARITY_MULT", 1.18, 0.4, 2.2)



# =============================================================================
# NAV: RUNTIME_DUMPS_AND_ITEM_LOOKUP
# =============================================================================
def load_item_knowledge() -> dict[str, Any]:
    if not KNOWLEDGE_ENABLED:
        return {"items": {}, "patterns": []}
    try:
        if ITEM_KNOWLEDGE_PATH.exists():
            return json.loads(ITEM_KNOWLEDGE_PATH.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"[InfiniCrafterLocal] item knowledge load failed: {e!r}")
    return {"items": {}, "patterns": []}


ITEM_KNOWLEDGE = load_item_knowledge()

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

def safe_file_part(text: Any, default: str = "value", max_len: int = 80) -> str:
    return world_storage.safe_file_part(text, default, max_len)



# =============================================================================
# NAV: WORLD_CACHE_AND_STORAGE
# =============================================================================
def world_recipe_dir(world_id: Any) -> Path:
    # Directory is keyed by the real Terraria worldId. worldName is metadata only,
    # because a human-readable name may change while recipe discovery should stay
    # tied to the world identity.
    return world_storage.world_recipe_dir(WORLD_RECIPES_DIR, world_id)


def world_recipe_file(world_id: Any, recipe_key_value: str) -> Path:
    return world_storage.world_recipe_file(WORLD_RECIPES_DIR, world_id, recipe_key_value)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    world_storage.atomic_write_json(path, payload)


def read_json_file(path: Path) -> dict[str, Any] | None:
    return world_storage.read_json_file(path)


def write_world_manifest(world_id: Any, world_name: Any = None) -> None:
    world_storage.write_world_manifest(WORLD_RECIPES_DIR, APP_VERSION, world_id, world_name)


def update_world_recipe_index(world_id: Any, recipe_key_value: str, data: dict[str, Any], a: Any = None, b: Any = None, world_name: Any = None) -> None:
    world_storage.update_world_recipe_index(
        WORLD_RECIPES_DIR,
        recipe_key_value,
        data,
        world_id=world_id,
        parent_a_name=name_of(a) if isinstance(a, dict) else data.get("recipeMeta", {}).get("parentA", ""),
        parent_b_name=name_of(b) if isinstance(b, dict) else data.get("recipeMeta", {}).get("parentB", ""),
        world_name=world_name,
    )




















def strip_runtime_only_fields(data: dict[str, Any]) -> dict[str, Any]:
    return world_storage.strip_runtime_only_fields(data)


def _delivery_safe_debug(debug: Any) -> dict[str, str]:
    return world_storage.delivery_safe_debug(debug)


def sanitize_recipe_for_delivery(data: Any) -> Any:
    return world_storage.sanitize_recipe_for_delivery(data)


def write_world_recipe_cache(recipe_key_value: str, world_id: Any, data: dict[str, Any], a: Any = None, b: Any = None, world_name: Any = None) -> None:
    world_storage.write_world_recipe_cache(
        WORLD_RECIPES_DIR,
        APP_VERSION,
        recipe_key_value,
        world_id,
        data,
        parent_a_name=name_of(a) if isinstance(a, dict) else data.get("recipeMeta", {}).get("parentA", ""),
        parent_b_name=name_of(b) if isinstance(b, dict) else data.get("recipeMeta", {}).get("parentB", ""),
        world_name=world_name,
    )


def read_world_recipe_cache(recipe_key_value: str, world_id: Any, world_name: Any = None) -> dict[str, Any] | None:
    return world_storage.read_world_recipe_cache(
        WORLD_RECIPES_DIR,
        APP_VERSION,
        RECIPE_IDENTITY_VERSION,
        recipe_key_value,
        world_id,
        world_name,
    )


def is_deliverable_recipe_payload(data: Any) -> bool:
    return world_storage.is_deliverable_recipe_payload(data)


def log_event(level: str, message: str, payload: Any = None) -> None:
    trace_tools.log_event(CACHE_DIR, level, message, payload)


def _trace_clip(value: Any, max_chars: int | None = None) -> str:
    return trace_tools.trace_clip(value, default_max_chars=TRACE_MAX_PROMPT_CHARS, max_chars=max_chars)


def _trace_message_summary(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return trace_tools.trace_message_summary(messages)


def trace_event(kind: str, stage: str, title: str, payload: Any = None, *, prompt: Any = None, negative: Any = None, response: Any = None, error: Any = None) -> None:
    trace_tools.trace_event(
        cache_dir=CACHE_DIR,
        trace_prompts_enabled=TRACE_PROMPTS_ENABLED,
        trace_max_prompt_chars=TRACE_MAX_PROMPT_CHARS,
        trace_file=TRACE_FILE,
        prompt_trace_file=PROMPT_TRACE_FILE,
        kind=kind,
        stage=stage,
        title=title,
        payload=payload,
        prompt=prompt,
        negative=negative,
        response=response,
        error=error,
    )


def _tail_text_file(path: str | Path, max_chars: int = 16000) -> str:
    return trace_tools.tail_text_file(path, max_chars)


def _tail_ndjson(path: str | Path, limit: int = 80) -> list[dict[str, Any]]:
    return trace_tools.tail_ndjson(path, limit)


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


def cache_get(key: str, world_id: Any | None = None, world_name: Any = None) -> dict[str, Any] | None:
    # Primary and only gameplay storage: explicit per-world recipe files.
    if world_id is None:
        return None
    return read_world_recipe_cache(key, world_id, world_name)


def cache_put(key: str, a: dict[str, Any], b: dict[str, Any], data: dict[str, Any], world_id: Any | None = None, world_name: Any = None) -> None:
    # No old-storage mirror. If this is a gameplay recipe, it must be world-scoped.
    if world_id is None:
        raise WorldScopeMissing("missing worldId while writing recipe; refusing non-world recipe storage")
    write_world_recipe_cache(key, world_id, data, a, b, world_name)


# -----------------------------------------------------------------------------
# Canonicalization
# -----------------------------------------------------------------------------



PALETTES = {
    "wood": ["brown", "tan", "dark_brown"],
    "wire": ["dark_gray", "yellow"],
    "electric": ["yellow", "cyan", "white"],
    "star": ["gold", "white", "blue"],
    "daybloom": ["yellow", "green", "white"],
    "flower": ["green", "yellow", "pink"],
    "slime": ["green", "cyan"],
    "shadow": ["purple", "black"],
    "fire": ["orange", "red", "yellow"],
    "ice": ["cyan", "white", "blue"],
    "technology": ["dark_gray", "cyan", "blue"],
    "accessory": ["silver", "gold", "blue"],
    "boots": ["brown", "silver", "blue"],
    "wings": ["white", "blue", "gold"],
    "shield": ["gray", "silver", "dark_gray"],
    "emblem": ["gold", "red", "white"],
    "charm": ["gold", "purple", "cyan"],
    "tool": ["brown", "gray", "silver"],
    "axe": ["brown", "steel", "green"],
    "drill": ["gray", "yellow", "blue"],
    "ammo": ["gray", "brass", "red"],
    "armor": ["gray", "silver", "blue"],
    "dirt": ["brown", "tan", "dark_brown"],
    "earth": ["brown", "green", "tan"],
    "stone": ["gray", "dark_gray", "white"],
    "sand": ["tan", "yellow", "white"],
    "block": ["gray", "brown", "tan"],
    "material": ["gray", "tan", "white"],
    "coin": ["gold", "silver", "copper"],
}


def recipe_key(a: dict[str, Any], b: dict[str, Any], world_id: Any, recipe_identity_version: str = RECIPE_IDENTITY_VERSION) -> str:
    return _world_recipe_key(a, b, world_id, recipe_identity_version)


# =============================================================================
# NAV: ITEM_FINGERPRINT_AND_SIGNALS
# =============================================================================






















def behavior_cost_multiplier(genome: dict[str, Any]) -> float:
    """Reference economy estimate, not the author of final stats.

    In production runtime-authoring mode this value is used for fallback/diagnostics and
    emergency sanity, not as a deterministic rewrite of sane LLM-authored damage.
    """
    shot_count = max(1.0, float(genome.get("shotCount") or 1))
    raw_pierce_for_cost = float(genome.get("pierce") if genome.get("pierce") is not None else 0)
    pierce = 8.0 if int(raw_pierce_for_cost) == -1 else max(0.0, raw_pierce_for_cost)
    aoe = max(0.0, float(genome.get("aoeRadiusTiles") or 0))
    homing = max(0.0, min(1.0, float(genome.get("homingStrength") or 0)))
    lifetime = max(20.0, min(1200.0, float(genome.get("lifetimeTicks") or 90)))
    extra_updates = max(0.0, min(3.0, float(genome.get("extraUpdates") or 0)))
    reliability = max(0.35, min(1.35, float(genome.get("reliability") or 1.0)))
    range_tiles = max(3.0, min(120.0, float(genome.get("rangeTiles") or 35)))
    self_lock = max(0.0, min(120.0, float(genome.get("selfLockTicks") or 0)))
    miss_punish = max(0.0, min(1.0, float(genome.get("missPunish") or 0)))
    child_pressure = _child_spawn_estimate(genome)
    cost = 1.0
    cost *= 1.0 + (shot_count - 1.0) * 0.55
    cost *= 1.0 + min(1.35, pierce * 0.22)
    cost *= 1.0 + min(2.4, (aoe ** 1.55) * 0.045)
    cost *= 1.0 + homing * 0.72
    cost *= 1.0 + min(0.55, max(0.0, lifetime - 90.0) / 700.0)
    cost *= 1.0 + extra_updates * 0.16
    cost *= 1.0 + min(0.32, max(0.0, range_tiles - 35.0) / 220.0)
    cost *= 1.0 + min(1.10, child_pressure * 0.075)
    cost *= reliability
    discount = 1.0 + min(0.65, self_lock / 150.0) + miss_punish * 0.22
    return max(0.35, cost / discount)


def _child_spawn_estimate(genome: dict[str, Any]) -> float:
    onhit = str(genome.get("onHit") or "none")
    shot_count = max(1.0, float(genome.get("shotCount") or 1))
    aoe = max(0.0, float(genome.get("aoeRadiusTiles") or 0))
    if onhit in {"split"}:
        return max(0.0, min(8.0, float(genome.get("splitCount") if genome.get("splitCount") is not None else max(0.0, aoe + shot_count - 1.0))))
    if onhit in {"chain", "lightning_arc"}:
        authored = genome.get("chainCount") if genome.get("chainCount") is not None else genome.get("splitCount")
        if authored is not None:
            return max(0.0, min(8.0, float(authored or 0)))
        return 3.0 if onhit == "lightning_arc" else 2.0
    if onhit in {"starburst", "starfall", "radial_beams", "spore_cloud", "mini_missiles", "vortex_spawn"}:
        authored = genome.get("splitCount") if genome.get("splitCount") is not None else genome.get("maxChildProjectiles")
        if authored is not None:
            return max(0.0, min(8.0, float(authored or 0)))
        if onhit in {"starburst", "starfall", "radial_beams"}:
            return 7.0
        if onhit in {"spore_cloud", "mini_missiles"}:
            return min(8.0, 3.0 + aoe * 0.6)
        return 3.0
    return 0.0


def estimate_engine_metrics(genome: dict[str, Any], stage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derived engine-pressure metrics. These are functions, not LLM tags.

    Terraria has real Dust fields such as scale/alpha/velocity/fadeIn, but no universal
    'intensity'. We therefore estimate pressure from spawned projectiles, lifetime, useTime
    and dust emission cadence. This is a technical safety rail, not a fun/boring evaluator.
    """
    stage = stage or {}
    use_time = max(6.0, float(genome.get("useTimeTicks") or stage.get("useTime") or 24))
    shot_count = max(1.0, float(genome.get("shotCount") or 1))
    lifetime = max(10.0, min(1200.0, float(genome.get("lifetimeTicks") or 90)))
    extra_updates = max(0.0, min(3.0, float(genome.get("extraUpdates") or 0)))
    reliability = max(0.05, min(1.35, float(genome.get("reliability") or 1.0)))
    uses_per_second = 60.0 / use_time
    active_primary = shot_count * uses_per_second * (lifetime / 60.0)
    child_per_proc = _child_spawn_estimate(genome)
    # Children are usually proc-gated/on-hit and depth-limited, so this is intentionally conservative.
    child_pressure = child_per_proc * uses_per_second * reliability * 0.55
    active_projectiles = active_primary + child_pressure
    raw_dust = genome.get("dustSpawnDenom")
    try:
        dust_denom = float(raw_dust) if raw_dust is not None else 3.0
    except Exception:
        dust_denom = 3.0
    if dust_denom <= 0:
        dust_per_second = min(30.0, child_per_proc * 2.0)
    else:
        dust_denom = max(2.0, min(20.0, dust_denom))
        dust_per_second = active_projectiles * (60.0 / dust_denom) + min(30.0, child_per_proc * 2.0)
    sync_pressure = active_projectiles * (1.0 + extra_updates * 0.22)
    return {
        "usesPerSecond": round(uses_per_second, 3),
        "activePrimaryProjectiles": round(active_primary, 3),
        "childProjectilesPerProc": round(child_per_proc, 3),
        "activeProjectileEstimate": round(active_projectiles, 3),
        "dustPerSecondEstimate": round(dust_per_second, 3),
        "networkSyncPressureEstimate": round(sync_pressure, 3),
    }


def sanitize_genome_engine(genome: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    """Clamp only engine-pressure outliers. Does not judge creativity or similarity."""
    g = dict(genome)
    power = max(0.5, float(stage.get("powerBudget") or 1.0))
    max_active = 22.0 + power * 8.0
    max_sync = 26.0 + power * 8.0

    # First pass: technical pressure only. Preserve long-lived identity (orbit/boomerang/field)
    # unless the entity budget is actually unsafe; prefer trimming multiplicity/extraUpdates
    # before shortening lifetime. This keeps the validator from becoming a deterministic designer.
    for _ in range(5):
        metrics = estimate_engine_metrics(g, stage)
        if metrics["activeProjectileEstimate"] <= max_active and metrics["networkSyncPressureEstimate"] <= max_sync:
            break
        if int(g.get("shotCount") or 1) > 1:
            g["shotCount"] = max(1, int(g.get("shotCount") or 1) - 1)
        elif int(g.get("extraUpdates") or 0) > 0:
            g["extraUpdates"] = max(0, int(g.get("extraUpdates") or 0) - 1)
        elif float(g.get("lifetimeTicks") or 90) > 45:
            long_lived = str(g.get("movement") or "") in {"orbit", "boomerang", "returning_glaive", "drift", "vortex_orb", "blackhole_pull", "expanding_wave"}
            floor = 80 if long_lived else 35
            g["lifetimeTicks"] = max(floor, int(float(g.get("lifetimeTicks") or 90) * (0.88 if long_lived else 0.80)))
        else:
            break

    metrics = estimate_engine_metrics(g, stage)
    # Derived runtime knobs for C# projectile implementation. In v0.4.3 child projectiles
    # are only allocated when the LLM explicitly authored a secondary-projectile/on-hit child plan.
    child_estimate = int(max(0, round(_child_spawn_estimate(g))))
    child_requested = child_estimate > 0 or int(float(g.get("splitCount") or 0)) > 0
    if child_requested:
        authored_cap = int(float(g.get("maxChildProjectiles") or 0))
        exact_cap = authored_cap if authored_cap > 0 else max(1, child_estimate)
        g["maxChildProjectiles"] = int(max(1, min(36, exact_cap)))
        g["maxChildDepth"] = 1
    else:
        g["maxChildProjectiles"] = 0
        g["maxChildDepth"] = 0

    # Dust in Terraria is controlled by actual emission frequency/scale/alpha calls.
    # Preserve explicit 0 from runtimePlan: 0 means no ambient dust.
    target_dust_per_second = 120.0 + power * 24.0
    if g.get("dustSpawnDenom") is None:
        denom = int(max(2, min(20, 3 + max(0.0, metrics["activeProjectileEstimate"] - 8.0) / 3.0)))
        g["dustSpawnDenom"] = denom
        for _ in range(4):
            metrics = estimate_engine_metrics(g, stage)
            if metrics["dustPerSecondEstimate"] <= target_dust_per_second or int(g["dustSpawnDenom"]) >= 20:
                break
            g["dustSpawnDenom"] = int(g["dustSpawnDenom"]) + 2
    else:
        try:
            g["dustSpawnDenom"] = int(max(0, min(20, float(g.get("dustSpawnDenom")))))
        except Exception:
            g["dustSpawnDenom"] = 0
    metrics = estimate_engine_metrics(g, stage)

    # Burst dust is visual feedback, not damage. Preserve authored 0 for ambient/no-hit
    # dust, but a concrete burst-style on-hit executor needs at least a tiny visual cap.
    if g.get("burstDustCap") is None:
        g["burstDustCap"] = int(max(0, min(28, 6 + power * 2)))
    else:
        try:
            g["burstDustCap"] = int(max(0, min(28, float(g.get("burstDustCap")))))
        except Exception:
            g["burstDustCap"] = 0
    onhit_key = str(g.get("onHit") or "").strip().lower()
    try:
        onhit_code = int(float(g.get("onHitCode") or 0))
    except Exception:
        onhit_code = 0
    if int(g.get("burstDustCap") or 0) <= 0 and onhit_uses_burst_dust_feedback(onhit_key, onhit_code):
        g["burstDustCap"] = int(max(4, min(24, 6 + power * 2)))
        g.setdefault("engineSanityRepairs", []).append("burst_onhit_requires_nonzero_burstDustCap")
    g["engineMetrics"] = metrics
    return g


def clamp_float(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return default


def dict_get_ci(d: dict[str, Any], name: str, default: Any = None) -> Any:
    if not isinstance(d, dict):
        return default
    if name in d:
        return d.get(name)
    pascal = name[:1].upper() + name[1:]
    if pascal in d:
        return d.get(pascal)
    lower = name.lower()
    for k, v in d.items():
        if str(k).lower() == lower:
            return v
    return default


def fingerprint_tags(item: dict[str, Any]) -> set[str]:
    """Mechanics-derived tags. This is deliberately independent from rarity."""
    tags: set[str] = set()
    if item_num(item, "damage") > 0:
        tags.add("weapon")
    dc = str(item_field(item, "damageClass", "") or "").lower()
    if dc in {"melee", "ranged", "magic", "summon"}:
        tags.update({"weapon", dc})
    if item_bool(item, "accessory"):
        tags.add("accessory")
    if item_num(item, "defense") > 0 or item_num(item, "headSlot", -1) >= 0 or item_num(item, "bodySlot", -1) >= 0 or item_num(item, "legSlot", -1) >= 0:
        tags.add("armor")
    if item_num(item, "pickPower") > 0:
        tags.update({"tool", "pickaxe"})
    if item_num(item, "axePower") > 0:
        tags.update({"tool", "axe"})
    if item_num(item, "hammerPower") > 0:
        tags.update({"tool", "hammer"})
    if item_num(item, "healLife") > 0 or item_num(item, "healMana") > 0:
        tags.update({"potion", "consumable"})
    if item_num(item, "ammo") > 0 or item_num(item, "useAmmo") > 0:
        tags.add("ammo")
    if item_num(item, "shoot") > 0 and item_num(item, "damage") > 0:
        tags.add("projectile")
    tags |= projectile_behavior_tags(item)
    if item_num(item, "createTile", -1) >= 0 or item_num(item, "createWall", -1) >= 0:
        tags.add("placeable")
    if item_bool(item, "consumable"):
        tags.add("consumable")
    return tags



def is_currency_ammo_item(item: dict[str, Any], tags: set[str] | None = None) -> bool:
    """Coins are ammo/currency, not a full weapon anchor by themselves.

    Money Gun exists, so coin damage fields are real Terraria data, but a lone coin
    parent should not transfer lunar/post-Moon-Lord combat tier into generated tosses.
    """
    tags = set(tags or tags_of(item))
    return bool(
        "coin" in tags
        and "ammo" in tags
        and item_bool(item, "consumable")
        and item_num(item, "ammo", 0) > 0
        and item_num(item, "useAmmo", 0) <= 0
        and item_num(item, "maxStack", 1) > 1
    )


def is_low_tier_consumable_projectile_item(item: dict[str, Any], tags: set[str] | None = None) -> bool:
    """Stackable starter projectiles are real raw facts, but poor progression anchors.

    Shuriken/throwing-knife/low dart-like parents can have excellent theoretical DPS
    when priced as free weapons.  In Terraria they are stackable consumables, so their
    raw projectile profile should still reach the LLM, but their inferred tier signal
    must not become hardmode just because useTime is low and pierce exists.
    """
    tags = set(tags or tags_of(item))
    return bool(
        item_bool(item, "consumable")
        and item_num(item, "maxStack", 1) > 1
        and 0 < item_num(item, "damage", 0) <= 25
        and item_num(item, "shoot", 0) > 0
        and item_num(item, "useAmmo", 0) <= 0
        and not item_bool(item, "channel")
        and (tags & {"ammo", "throwing", "ranged", "projectile", "dart", "shuriken", "knife", "consumable", "weapon"})
    )


def is_simple_low_tier_melee_weapon(item: dict[str, Any], tags: set[str] | None = None) -> bool:
    tags = set(tags or tags_of(item))
    return bool(
        item_num(item, "damage", 0) > 0
        and item_num(item, "damage", 0) <= 20
        and item_num(item, "shoot", 0) <= 0
        and not item_bool(item, "noMelee")
        and ("melee" in tags or str(item_field(item, "damageClass", "")).lower() == "melee")
    )

def mechanic_signal_power(item: dict[str, Any]) -> dict[str, Any]:
    """Item strength fingerprint.

    Runtime strength fingerprint. The runtime may use live stats, projectile behavior, rarity metadata and broad classification hints, but not hand-authored recipe graphs or per-item power-oracle tables.
    """
    dmg = item_num(item, "damage")
    pick = item_num(item, "pickPower")
    axe = item_num(item, "axePower")
    hammer = item_num(item, "hammerPower")
    defense = item_num(item, "defense")
    heal_life = item_num(item, "healLife")
    heal_mana = item_num(item, "healMana")
    mana = item_num(item, "manaCost", item_num(item, "mana"))
    shoot = item_num(item, "shoot")
    shoot_speed = item_num(item, "shootSpeed")
    knock = item_num(item, "knockback", item_num(item, "knockBack"))
    value = item_num(item, "value")
    tags = tags_of(item)
    category = parent_primary_category(item)

    behavior = source_weapon_profile(item)
    behavior_signal = 0.0
    currency_ammo = is_currency_ammo_item(item, tags)
    consumable_projectile_anchor = is_low_tier_consumable_projectile_item(item, tags)
    simple_low_melee = is_simple_low_tier_melee_weapon(item, tags)
    if dmg > 0:
        behavior_signal = min(260.0, math.sqrt(max(0.0, float(behavior.get("effectiveDpsSignal") or 0))) * 12.0)
        if simple_low_melee:
            # Raw DPS on a fast starter melee item is not a boss-tier signal.
            behavior_signal = min(behavior_signal, dmg * 3.0 + 8.0)
        if currency_ammo:
            # Money Gun makes coin damage meaningful, but the coin alone is an ammo/currency
            # source, not a full weapon parent. Preserve the signal, but cap stage pressure.
            behavior_signal = min(behavior_signal, dmg * 0.45 + 14.0)
        if consumable_projectile_anchor:
            # Stackable starter projectiles are consumables, not reusable hardmode weapons.
            behavior_signal = min(behavior_signal, dmg * 2.4 + 18.0)

    # Practical power, not raw projectile theory. Avoid per-item exception tables here;
    # consumable/stack penalties are handled by generic economy fields and stage caps.
    damage_signal = max(
        dmg * 1.05 + min(10.0, knock * 1.2) + (8.0 if shoot > 0 and dmg > 0 else 0.0) + min(10.0, shoot_speed * 0.75),
        behavior_signal,
    )
    if simple_low_melee:
        damage_signal = min(damage_signal, dmg * 3.0 + 10.0)
    if currency_ammo:
        coin_value_hint = min(8.0, (value ** 0.5) * 0.14 if value > 0 else 0.0)
        damage_signal = min(damage_signal, dmg * 0.55 + 18.0 + coin_value_hint)
    if consumable_projectile_anchor:
        projectile_value_hint = min(6.0, (value ** 0.5) * 0.08 if value > 0 else 0.0)
        damage_signal = min(damage_signal, dmg * 2.35 + 20.0 + projectile_value_hint)
    tool_signal = max(pick * 1.35, axe * 7.0, hammer * 1.25)
    armor_signal = defense * 8.0
    heal_signal = max(heal_life * 0.55, heal_mana * 0.65)
    magic_signal = mana * 2.2 if dmg > 0 else 0.0
    value_signal = min(90.0, (value ** 0.5) * 0.14) if value > 0 else 0.0

    rarity = rarity_baseline_signal(item, tags, category)
    rarity_signal = float(rarity.get("convertedPower") or 0.0)
    generic_mod_signal = generic_modded_progression_signal(item, tags, category, rarity)
    generic_mod_score = float(generic_mod_signal.get("score") or 0.0)

    primary = max(damage_signal, tool_signal, armor_signal, heal_signal, magic_signal)
    # Rarity is a strong baseline for unknown high-tier items, not just a tiny tie-breaker.
    # But mechanics still matter: if we have real combat/tool/armor stats, use them and add a small rarity lift.
    if primary <= 0:
        score = max(rarity_signal, value_signal, generic_mod_score)
        if generic_mod_score >= max(rarity_signal, value_signal):
            basis = "generic_modded_progression_signal"
        else:
            basis = "rarity_baseline" if rarity_signal >= value_signal else "value_baseline"
    else:
        score = max(primary, rarity_signal * 0.72, generic_mod_score) + min(max(value_signal, rarity_signal), 90.0) * 0.18
        basis = "mechanics_plus_rarity_baseline" if generic_mod_score <= max(primary, rarity_signal * 0.72) else "mechanics_plus_generic_modded_progression"
    if currency_ammo:
        score = min(score, 72.0)
        basis = (basis + "+currency_ammo_cap")[:80]
    if consumable_projectile_anchor:
        score = min(score, 54.0)
        basis = (basis + "+consumable_projectile_cap")[:80]
    if simple_low_melee:
        score = min(score, 42.0)
        basis = (basis + "+starter_melee_cap")[:80]
    return {
        "score": round(max(0.0, score), 2),
        "basis": basis,
        "damageSignal": round(damage_signal, 2),
        "toolSignal": round(tool_signal, 2),
        "armorSignal": round(armor_signal, 2),
        "healSignal": round(heal_signal, 2),
        "valueSignal": round(value_signal, 2),
        "raritySignal": round(rarity_signal, 2),
        "genericModdedSignal": generic_mod_signal,
        "rarityBaseline": rarity,
        "weaponBehavior": behavior,
    }


def generation_depth(item: dict[str, Any]) -> int:
    gd = generated_data_of(item)
    if not gd:
        return 0
    meta_raw = dict_get_ci(gd, "recipeMeta", {})
    debug_raw = dict_get_ci(gd, "debug", {})
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    debug = debug_raw if isinstance(debug_raw, dict) else {}
    for source in (meta, debug):
        for key in ("generationDepth", "depth"):
            try:
                if key in source:
                    return max(1, int(float(source[key])))
            except Exception:
                pass
    return 1



def recipe_coherence(tags: set[str], a: dict[str, Any], b: dict[str, Any]) -> str:
    # This is deliberately broad: every pair is valid, but the corridor changes.
    if generation_depth(a) > 0 or generation_depth(b) > 0:
        return "recursive"
    hard = tags & HARD_TAGS
    if len(hard) >= 3:
        return "strong"
    if len(hard) >= 1 or max(int(a.get("damage") or 0), int(b.get("damage") or 0)) > 0:
        return "weak"
    return "nonsense"


def recipe_meta(a: dict[str, Any], b: dict[str, Any], tags: set[str], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    depths = [generation_depth(a), generation_depth(b)]
    coherence = recipe_coherence(tags, a, b)
    return {
        "universalRecipe": True,
        "generationDepth": max(depths) + 1,
        "parentGeneratedDepths": depths,
        "recipeCoherence": coherence,
        "chaosBudget": round(min(1.0, CATEGORY_CREATIVITY + 0.07 * max(depths) + (0.12 if coherence in {"weak", "nonsense"} else 0.0)), 3),
        "noveltyBudget": round(min(1.0, 0.18 + 0.08 * max(depths) + (0.18 if coherence == "recursive" else 0.0)), 3),
        "parentIdentities": [item_identity(a), item_identity(b)],
        "parentCategories": [parent_primary_category(a), parent_primary_category(b)],
        "sampledLane": (policy or {}).get("lane", ""),
        "sampledCategory": (policy or {}).get("selected", ""),
    }




def is_material_parent(item: dict[str, Any]) -> bool:
    cat = parent_primary_category(item)
    return cat == "material" or "material" in tags_of(item)


def material_catalyst_pressure(item: dict[str, Any], weapon_tags: set[str] | None = None) -> dict[str, Any]:
    """Broad progression/crafting pressure for non-weapon ingredients.

    This is not a recipe graph and does not know that A+B=C. It only detects that a
    material looks like a serious progression catalyst: high rarity/value, hardmode/lunar
    tags, fragments/bars/souls/hero pieces, and optional class alignment with the weapon.
    The goal is to let routes like Minishark + hardmode gun materials climb without
    writing per-item recipes, while Dirt/Wood/Torch remain weak anchors.
    """
    tags = tags_of(item)
    weapon_tags = weapon_tags or set()
    rare = int(item_num(item, "rare", 0))
    value = max(0.0, item_num(item, "value", 0))
    pressure = 0.0
    reasons: list[str] = []
    if not is_material_parent(item):
        return {"pressure": 0.0, "reasons": []}
    if tags & {"dirt", "wood", "stone", "sand", "block", "torch", "gel"}:
        pressure -= 0.45
        reasons.append("primitive_or_common_material")
    if rare >= 2:
        pressure += min(0.85, rare * 0.08)
        reasons.append("rarity")
    if value >= 10000:
        pressure += min(0.75, math.sqrt(value) / 520.0)
        reasons.append("value")
    if tags & {"hardmode", "soul", "mech", "hero", "hallowed", "chlorophyte", "crystal"}:
        pressure += 0.45
        reasons.append("hardmode_catalyst")
    if tags & {"fragment", "lunar", "solar", "vortex", "nebula", "stardust", "luminite", "moon_lord"}:
        pressure += 0.85
        reasons.append("lunar_catalyst")
    if tags & {"bar", "ore"}:
        pressure += 0.22
        reasons.append("bar_or_ore")
    if tags & {"soul", "fragment", "hero"}:
        pressure += 0.18
        reasons.append("rare_crafting_part")
    # Class/thematic alignment: Vortex with ranged, Nebula with magic, Broken Hero Sword with melee, etc.
    if weapon_tags & tags & {"melee", "ranged", "magic", "summon", "sword", "blade", "gun", "bow"}:
        pressure += 0.35
        reasons.append("class_or_weapon_family_alignment")
    elif ("ranged" in weapon_tags and tags & {"gun", "bullet", "vortex"}) or ("magic" in weapon_tags and tags & {"mana", "nebula", "crystal"}) or ("melee" in weapon_tags and tags & {"sword", "blade", "hero"}):
        pressure += 0.35
        reasons.append("class_catalyst_alignment")
    pressure = max(0.0, min(2.2, pressure))
    return {"pressure": round(pressure, 3), "reasons": reasons}


def pair_catalyst_pressure(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    ta, tb = tags_of(a), tags_of(b)
    pa = material_catalyst_pressure(a, tb)
    pb = material_catalyst_pressure(b, ta)
    total = max(float(pa.get("pressure") or 0), float(pb.get("pressure") or 0))
    return {"pressure": round(total, 3), "left": pa, "right": pb}

def lower_name(item: dict[str, Any]) -> str:
    return name_of(item).lower()


def tags_of(item: dict[str, Any]) -> set[str]:
    # Internal tags are mechanically derived from runtime fields/name tokens/generated parents.
    # Vanilla/modded input payloads do not need hand-authored semantic tags.
    tags = {str(t).lower() for t in item.get("tags", []) if str(t).strip()}
    tags |= {str(t).lower() for t in item.get("autoFeatures", []) if str(t).strip()}
    tags |= {str(t).lower() for t in item.get("nameTokens", []) if str(t).strip()}
    gd = item.get("generatedData")
    if isinstance(gd, dict):
        tags |= {str(t).lower() for t in dict_get_ci(gd, "tags", []) if str(t).strip()}
        can = dict_get_ci(gd, "canonical", {}) or {}
        tags |= {str(t).lower() for t in dict_get_ci(can, "hardTags", []) if str(t).strip()}
        tags |= {str(t).lower() for t in dict_get_ci(can, "softTags", []) if str(t).strip()}
    fp = fingerprint_of(item)
    if isinstance(fp, dict):
        tags |= {str(t).lower() for t in fp.get("autoFeatures", []) if str(t).strip()}
        tags |= {str(t).lower() for t in fp.get("nameTokens", []) if str(t).strip()}
    tags |= fingerprint_tags(item)
    source_mod = str(item_field(item, "sourceMod", "Terraria") or "")
    if source_mod and source_mod.lower() != "terraria":
        tags.add("modded")
        tags.add("mod_" + slug(source_mod))
    names_blob = " ".join(str(x or "") for x in [
        name_of(item),
        item_field(item, "internalName", ""),
        item_field(item, "fullName", ""),
        item_field(item, "typeName", ""),
    ]).lower()
    n = names_blob
    def add_if(substr: str, *add: str):
        if substr in n:
            tags.update(add)
    add_if("wooden", "wood")
    add_if("wood", "wood")
    add_if("dirt", "dirt", "earth", "block", "material", "placeable")
    add_if("stone", "stone", "block", "material", "placeable")
    add_if("sand", "sand", "block", "material", "placeable")
    add_if("mud", "mud", "earth", "block", "material", "placeable")
    add_if("clay", "clay", "earth", "block", "material", "placeable")
    add_if("block", "block", "material", "placeable")
    add_if("ore", "ore", "material")
    add_if("bar", "bar", "material")
    add_if("coin", "coin", "material")
    add_if("chair", "chair", "furniture", "placeable")
    add_if("wire", "wire", "electric", "mechanism")
    add_if("electric", "electric")
    add_if("star", "star", "light", "mana")
    add_if("fallen star", "star", "light", "mana")
    add_if("daybloom", "daybloom", "flower", "plant", "day")
    add_if("sunflower", "sunflower", "flower", "plant", "sun", "day")
    add_if("flower", "flower", "plant")
    add_if("gel", "gel", "slime")
    add_if("slime", "slime")
    add_if("circuit", "circuit", "technology", "electric")
    add_if("work bench", "workbench", "bench", "crafting_station", "wood")
    add_if("workbench", "workbench", "bench", "crafting_station", "wood")
    add_if("computer", "computer", "technology", "screen")
    add_if("virtual reality", "vr", "headset", "technology")
    add_if("vr", "vr", "headset", "technology")
    add_if("headset", "headset", "technology")
    add_if("boot", "accessory", "mobility", "boots")
    add_if("treads", "accessory", "mobility", "boots")
    add_if("aglet", "accessory", "mobility", "aglet")
    add_if("anklet", "accessory", "mobility", "anklet")
    add_if("wing", "accessory", "mobility", "wings")
    add_if("shield", "accessory", "defense", "shield")
    add_if("guard", "accessory", "defense", "shield")
    add_if("emblem", "accessory", "damage", "emblem")
    add_if("charm", "accessory", "charm")
    add_if("ring", "accessory", "ring", "charm")
    add_if("band", "accessory", "band", "charm")
    add_if("necklace", "accessory", "necklace", "charm")
    add_if("amulet", "accessory", "amulet", "charm")
    add_if("glove", "accessory", "melee", "glove")
    add_if("claw", "accessory", "melee", "glove")
    add_if("balloon", "accessory", "mobility", "balloon")
    add_if("horseshoe", "accessory", "mobility", "horseshoe")
    add_if("pickaxe", "tool", "pickaxe")
    add_if("hammer", "tool", "hammer")
    add_if("drill", "tool", "drill")
    add_if("axe", "tool", "axe")
    add_if("chainsaw", "tool", "chainsaw", "axe")
    add_if("hook", "grappling_hook", "hook")
    add_if("arrow", "ammo", "arrow")
    add_if("bullet", "ammo", "bullet")
    add_if("rocket", "ammo", "rocket", "explosive")
    add_if("helmet", "armor", "helmet")
    add_if("breastplate", "armor", "breastplate")
    add_if("greaves", "armor", "leggings")
    add_if("sword", "weapon", "melee", "sword")
    add_if("blade", "weapon", "melee", "blade")
    add_if("bow", "weapon", "ranged", "bow")
    add_if("gun", "weapon", "ranged", "gun")
    add_if("rifle", "weapon", "ranged", "gun")
    add_if("wand", "weapon", "magic", "wand")
    add_if("staff", "weapon", "magic", "staff")
    add_if("potion", "potion", "consumable")
    add_if("healing", "potion", "healing", "heal")
    add_if("lesserhealing", "potion", "healing", "heal")
    add_if("lesser healing", "potion", "healing", "heal")
    add_if("mana", "potion", "mana")
    add_if("glowstick", "glowstick", "light", "throwing", "projectile")
    add_if("glow stick", "glowstick", "light", "throwing", "projectile")
    add_if("mushroom", "mushroom", "plant", "consumable")
    add_if("glowingmushroom", "glowing", "mushroom", "light")
    add_if("glowing mushroom", "glowing", "mushroom", "light")
    add_if("shuriken", "weapon", "ranged", "throwing", "shuriken")
    add_if("throwingknife", "weapon", "ranged", "throwing", "knife")
    add_if("throwing knife", "weapon", "ranged", "throwing", "knife")
    add_if("knife", "weapon", "ranged", "throwing", "knife")
    add_if("banner", "banner", "furniture", "placeable")
    add_if("bomb", "bomb", "explosive", "throwing")
    add_if("grenade", "grenade", "explosive", "throwing")
    add_if("dynamite", "dynamite", "explosive", "throwing")
    add_if("obsidian", "obsidian", "lava", "fire")
    add_if("lava", "lava", "fire")
    # High-tier material keywords. These are only hints; exact tier comes from item_knowledge.json/runtime item facts.
    add_if("luminite", "luminite", "lunar", "moon_lord", "endgame_material", "material")
    add_if("solar fragment", "solar", "fragment", "lunar", "melee", "material")
    add_if("vortex fragment", "vortex", "fragment", "lunar", "ranged", "material")
    add_if("nebula fragment", "nebula", "fragment", "lunar", "magic", "material")
    add_if("stardust fragment", "stardust", "fragment", "lunar", "summon", "material")
    add_if("fragment", "fragment", "material")
    add_if("hallowed", "hallowed", "holy", "material")
    add_if("chlorophyte", "chlorophyte", "jungle", "plant", "material")
    add_if("shroomite", "shroomite", "mushroom", "ranged", "material")
    add_if("spectre", "spectre", "magic", "ghost", "material")
    add_if("beetle", "beetle", "golem", "material")
    add_if("auric", "auric", "tesla", "post_moonlord", "endgame_material", "material")
    add_if("cosmilite", "cosmilite", "cosmic", "post_moonlord", "endgame_material", "material")
    add_if("exodium", "exodium", "cosmic", "post_moonlord", "material")
    add_if("uelibloom", "uelibloom", "jungle", "post_moonlord", "material")
    add_if("shadowspec", "shadowspec", "shadow", "superboss", "endgame_material", "material")
    tags |= projectile_behavior_tags(item)
    if int(item.get("damage") or 0) > 0 and not (tags & (TOOL_HINT_TAGS | ARMOR_HINT_TAGS | ACCESSORY_HINT_TAGS | AMMO_HINT_TAGS)):
        tags.add("weapon")
    if item.get("accessory"):
        tags.add("accessory")
    if item.get("consumable"):
        tags.add("consumable")
    if int(item.get("createTile") or -1) >= 0:
        tags.add("placeable")
    return tags


def guess_head(name: str, tags: set[str]) -> str:
    for t in ["boots", "wings", "shield", "emblem", "charm", "ring", "glove", "accessory", "dirt", "stone", "sand", "block", "material", "chair", "wire", "headset", "computer", "circuit", "workbench", "bench", "potion", "sword", "blade", "bow", "gun", "wand", "staff", "flower", "daybloom", "star", "gel", "slime", "tool", "pickaxe", "axe", "hammer", "drill", "chainsaw", "ammo", "armor"]:
        if t in tags:
            return t
    parts = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", name)
    return (parts[-1].lower() if parts else "item")


def canonicalize(item: dict[str, Any]) -> dict[str, Any]:
    gd = item.get("generatedData")
    if isinstance(gd, dict) and gd.get("canonical"):
        c = dict(gd["canonical"])
        # Ensure arrays exist.
        for k in ["modifiers", "shapeAnchors", "visualAnchors", "hardTags", "softTags"]:
            c.setdefault(k, [])
        return c
    tags = tags_of(item)
    n = name_of(item)
    head = guess_head(n, tags)
    material = "wood" if "wood" in tags else "dirt" if "dirt" in tags or "earth" in tags else "stone" if "stone" in tags else "sand" if "sand" in tags else "iron" if "iron" in tags else "gold" if "gold" in tags else ""
    cls = "accessory" if "accessory" in tags else "weapon" if "weapon" in tags else "consumable" if "consumable" in tags else "tool" if "tool" in tags else "ammo" if "ammo" in tags else "armor" if "armor" in tags else "placeable" if "placeable" in tags else "material" if "material" in tags or "block" in tags else "generic"
    visual = []
    for tag in tags:
        visual.extend(VISUAL_SYNONYMS.get(tag, []))
    if not visual:
        visual = [n]
    hard = sorted(t for t in tags if t in HARD_TAGS)
    soft = sorted(t for t in tags if t not in hard)
    modifiers = []
    if "wood" in tags or "wooden" in n.lower():
        modifiers.append("wooden")
    if "virtual reality" in n.lower():
        modifiers.append("virtual reality")
    return {
        "headNoun": head,
        "modifiers": modifiers,
        "material": material,
        "class": cls,
        "shapeAnchors": sorted(set([head] + VISUAL_SYNONYMS.get(head, []))),
        "visualAnchors": sorted(set(visual)),
        "hardTags": hard,
        "softTags": soft,
    }


# -----------------------------------------------------------------------------
# Runtime item knowledge / classification cards
# -----------------------------------------------------------------------------

TIER_DEFAULT_POWER = {
    "trash": 2, "wood": 5, "early": 18, "pre_boss": 32, "evil_boss": 50,
    "pre_hardmode_late": 64, "hardmode_early": 82, "mech": 125,
    "plantera": 156, "post_plantera": 185, "post_golem": 205,
    "lunar": 235,
    # Vanilla Moon Lord / Zenith band. Important: Calamity post-ML tiers are intentionally far above this.
    "endgame": 285,
    # Calamity-like progression. These are crafting/progression anchors, not direct +damage values.
    "post_moonlord": 360, "post_moonlord_plus": 420,
    "superboss": 470, "devourer": 540, "auric": 660, "exo_yharon_plus": 720,
    "shadowspec": 750, "calamity_red_prefix": 790, "modded_high_unknown": 500, "superboss_unknown": 620,
    "draedon_arsenal": 320,
    # Result-only labels used when a huge Calamity material is mixed with a weak/basic anchor.
    "post_moonlord_influenced": 300, "devourer_influenced": 335, "auric_influenced": 370,
    "exo_yharon_plus_influenced": 410, "shadowspec_influenced": 425, "calamity_red_prefix_influenced": 440,
}

TIER_RANK = {
    "trash": 0, "wood": 1, "early": 2, "pre_boss": 3, "evil_boss": 4,
    "pre_hardmode_late": 5, "hardmode_early": 6, "mech": 7,
    "plantera": 8, "post_plantera": 9, "post_golem": 10,
    "lunar": 11, "endgame": 12,
    "post_moonlord": 13, "post_moonlord_plus": 14, "superboss": 15,
    "devourer": 16, "auric": 17, "exo_yharon_plus": 18, "shadowspec": 19, "calamity_red_prefix": 20,
    "draedon_arsenal": 13,
}

MODDED_HIGH_TIERS = {"post_moonlord", "post_moonlord_plus", "superboss", "devourer", "auric", "exo_yharon_plus", "shadowspec", "calamity_red_prefix"}
VANILLA_ENDGAME_POWER = TIER_DEFAULT_POWER["endgame"]


# Terraria vanilla rarity is an approximate progression signal.
# Calamity and other mods add real ModRarity classes; their runtime numeric ids are not stable semantic tiers.
# Prefer rarityDetails.name/mod/color when C# provides it, then fall back to raw Item.rare.
RARITY_BASELINE_TABLE = [
    (-99, "trash", 1, "Unknown", "#FFFFFF"),
    (-1, "trash", 2, "Gray", "#828282"),
    (0, "wood", 5, "White", "#FFFFFF"),
    (1, "early", 18, "Blue", "#9696FF"),
    (2, "pre_boss", 32, "Green", "#96FF96"),
    (3, "evil_boss", 50, "Orange", "#FFC896"),
    (4, "pre_hardmode_late", 64, "LightRed", "#FF9696"),
    (5, "hardmode_early", 82, "Pink", "#FF96FF"),
    (6, "mech", 125, "LightPurple", "#D2A0FF"),
    (7, "plantera", 156, "Lime", "#96FF0A"),
    (8, "post_plantera", 185, "Yellow", "#FFFF0A"),
    (9, "post_golem", 205, "Cyan", "#05C8FF"),
    (10, "lunar", 235, "Red", "#FF2864"),
    (11, "endgame", 285, "Purple", "#B428FF"),
]

# Semantic ladder for Calamity ModRarity classes. These are not just anonymous ids above 11:
# they have class names and colors in the mod code, and prefix rarity can shift them.
MODDED_RARITY_LADDER = {
    "calamitymod/turquoise": {"ordinal": 12, "tierEstimate": "post_moonlord", "tierScore": 360, "displayName": "Turquoise", "colorHex": "#00FFC8", "role": "calamity_rarity_class"},
    "turquoise": {"ordinal": 12, "tierEstimate": "post_moonlord", "tierScore": 360, "displayName": "Turquoise", "colorHex": "#00FFC8", "role": "calamity_rarity_class"},
    "calamitymod/puregreen": {"ordinal": 13, "tierEstimate": "post_moonlord_plus", "tierScore": 420, "displayName": "Pure Green", "colorHex": "#00FF00", "role": "calamity_rarity_class"},
    "puregreen": {"ordinal": 13, "tierEstimate": "post_moonlord_plus", "tierScore": 420, "displayName": "Pure Green", "colorHex": "#00FF00", "role": "calamity_rarity_class"},
    "pure green": {"ordinal": 13, "tierEstimate": "post_moonlord_plus", "tierScore": 420, "displayName": "Pure Green", "colorHex": "#00FF00", "role": "calamity_rarity_class"},
    "calamitymod/cosmicpurple": {"ordinal": 14, "tierEstimate": "devourer", "tierScore": 540, "displayName": "Cosmic Purple", "colorHex": "#CE84FF", "baseColorHex": "#67428A", "role": "calamity_rarity_class"},
    "cosmicpurple": {"ordinal": 14, "tierEstimate": "devourer", "tierScore": 540, "displayName": "Cosmic Purple", "colorHex": "#CE84FF", "baseColorHex": "#67428A", "role": "calamity_rarity_class"},
    "cosmic purple": {"ordinal": 14, "tierEstimate": "devourer", "tierScore": 540, "displayName": "Cosmic Purple", "colorHex": "#CE84FF", "baseColorHex": "#67428A", "role": "calamity_rarity_class"},
    "calamitymod/burnishedauric": {"ordinal": 15, "tierEstimate": "auric", "tierScore": 660, "displayName": "Burnished Auric", "colorHex": "#FFDC16", "baseColorHex": "#9D6E0B", "role": "calamity_rarity_class"},
    "burnishedauric": {"ordinal": 15, "tierEstimate": "auric", "tierScore": 660, "displayName": "Burnished Auric", "colorHex": "#FFDC16", "baseColorHex": "#9D6E0B", "role": "calamity_rarity_class"},
    "burnished auric": {"ordinal": 15, "tierEstimate": "auric", "tierScore": 660, "displayName": "Burnished Auric", "colorHex": "#FFDC16", "baseColorHex": "#9D6E0B", "role": "calamity_rarity_class"},
    "calamitymod/hotpink": {"ordinal": 16, "tierEstimate": "shadowspec", "tierScore": 750, "displayName": "Hot Pink", "colorHex": "#FF00FF", "role": "calamity_rarity_class"},
    "hotpink": {"ordinal": 16, "tierEstimate": "shadowspec", "tierScore": 750, "displayName": "Hot Pink", "colorHex": "#FF00FF", "role": "calamity_rarity_class"},
    "hot pink": {"ordinal": 16, "tierEstimate": "shadowspec", "tierScore": 750, "displayName": "Hot Pink", "colorHex": "#FF00FF", "role": "calamity_rarity_class"},
    "calamitymod/calamityred": {"ordinal": 17, "tierEstimate": "calamity_red_prefix", "tierScore": 790, "displayName": "Calamity Red", "colorHex": "#FF3636", "baseColorHex": "#F21B1B", "role": "calamity_rarity_class_prefix"},
    "calamityred": {"ordinal": 17, "tierEstimate": "calamity_red_prefix", "tierScore": 790, "displayName": "Calamity Red", "colorHex": "#FF3636", "baseColorHex": "#F21B1B", "role": "calamity_rarity_class_prefix"},
    "calamity red": {"ordinal": 17, "tierEstimate": "calamity_red_prefix", "tierScore": 790, "displayName": "Calamity Red", "colorHex": "#FF3636", "baseColorHex": "#F21B1B", "role": "calamity_rarity_class_prefix"},
    "calamitymod/darkorange": {"ordinal": 12, "tierEstimate": "draedon_arsenal", "tierScore": 320, "displayName": "Draedon's Arsenal / Rust / Bronze", "colorHex": "#CC4723", "role": "special_rarity_class"},
    "darkorange": {"ordinal": 12, "tierEstimate": "draedon_arsenal", "tierScore": 320, "displayName": "Draedon's Arsenal / Rust / Bronze", "colorHex": "#CC4723", "role": "special_rarity_class"},
}

MODDED_RARITY_COLOR_HINTS = {
    "#00FFC8": "turquoise",
    "#00FF00": "puregreen",
    "#CE84FF": "cosmicpurple",
    "#67428A": "cosmicpurple",
    "#FFDC16": "burnishedauric",
    "#9D6E0B": "burnishedauric",
    "#FF00FF": "hotpink",
    "#FF3636": "calamityred",
    "#F21B1B": "calamityred",
    "#CC4723": "darkorange",
}


def rarity_details_of(item: dict[str, Any]) -> dict[str, Any]:
    details = item.get("rarityDetails")
    if isinstance(details, dict):
        return details
    fp = fingerprint_of(item)
    details = fp.get("rarityDetails")
    return details if isinstance(details, dict) else {}


def _norm_rarity_key(text: Any) -> str:
    return knowledge_key(str(text or "")).replace(" ", "").replace("_", "").replace("-", "")


def _norm_hex(text: Any) -> str:
    h = str(text or "").strip().upper()
    if not h:
        return ""
    if not h.startswith("#"):
        h = "#" + h
    return h


def modded_rarity_entry(details: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(details, dict) or not details:
        return None
    name = str(details.get("name") or details.get("displayName") or "")
    mod = str(details.get("mod") or "")
    full = str(details.get("fullName") or (mod + "/" + name if mod or name else ""))
    candidates = {
        _norm_rarity_key(name),
        _norm_rarity_key(full),
        _norm_rarity_key(mod + "/" + name),
        knowledge_key(name),
        knowledge_key(full),
        knowledge_key(mod + "/" + name),
    }
    for cand in list(candidates):
        if cand in MODDED_RARITY_LADDER:
            return dict(MODDED_RARITY_LADDER[cand])
    color = _norm_hex(details.get("colorHex"))
    if color in MODDED_RARITY_COLOR_HINTS:
        key = MODDED_RARITY_COLOR_HINTS[color]
        if key in MODDED_RARITY_LADDER:
            return dict(MODDED_RARITY_LADDER[key])
    return None


def rarity_tier_estimate(raw_rare: int | float, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map Terraria/tModLoader rarity to an approximate tier.
    Exact item knowledge still wins; mod rarity class names/colors beat arbitrary runtime ids.
    """
    try:
        rare = int(raw_rare)
    except Exception:
        rare = 0

    details = details or {}
    modded = modded_rarity_entry(details)
    if modded:
        out = dict(modded)
        out.update({
            "rawRare": rare,
            "tierScore": float(out.get("tierScore") or 0),
            "confidence": 0.82,
            "runtimeRarityName": details.get("name"),
            "runtimeRarityMod": details.get("mod"),
            "runtimeColorHex": details.get("colorHex"),
        })
        return out

    if rare > 11:
        # Custom mod rarities can be arbitrary runtime ids. Without class-name knowledge,
        # derive a generic monotonic progression signal instead of falling back to weak vanilla rarity.
        ordinal = max(1, rare - 11)
        score = 340 + min(390, int((ordinal ** 0.74) * 55))
        tier = "modded_high_unknown" if score < 500 else "superboss_unknown"
        return {"rawRare": rare, "tierEstimate": tier, "tierScore": score, "confidence": 0.48, "role": "unknown_modded_numeric_rarity", "displayName": str(details.get("name") or "Unknown ModRarity"), "colorHex": details.get("colorHex"), "ordinal": ordinal}

    best_tier, best_score, best_name, best_hex = "trash", 1, "Unknown", "#FFFFFF"
    for threshold, tier, score, display, hex_color in RARITY_BASELINE_TABLE:
        if rare >= threshold:
            best_tier, best_score, best_name, best_hex = tier, score, display, hex_color
    conf = 0.66 if rare >= 0 else 0.46
    return {"rawRare": rare, "tierEstimate": best_tier, "tierScore": best_score, "confidence": conf, "role": "vanilla_rarity_baseline", "displayName": best_name, "colorHex": best_hex}


def rarity_role_weight(category: str, tags: set[str]) -> tuple[float, str]:
    category = normalize_category(category)
    if category == "weapon" or "weapon" in tags:
        return 1.00, "weapon rarity transfers to combat power"
    if category == "material" or "material" in tags or "bar" in tags or "fragment" in tags or "ore" in tags:
        return MATERIAL_RARITY_MULT, "material rarity transfers to crafting-tier power"
    if category == "tool" or "tool" in tags:
        return 0.92, "tool rarity transfers to utility/tool power"
    if category == "armor" or "armor" in tags:
        return 0.90, "armor rarity transfers to defense-tier power"
    if category == "accessory" or "accessory" in tags:
        return 0.82, "accessory rarity transfers to passive potential"
    if category in {"furniture", "placeable_station", "technology"} or "placeable" in tags or "block" in tags:
        return 0.66, "placeable rarity transfers mostly to tier/novelty"
    if category in {"vanity", "pet", "light_pet", "mount"}:
        return 0.50, "cosmetic rarity transfers mostly to novelty"
    return 0.70, "unknown role rarity baseline"


def rarity_baseline_signal(item: dict[str, Any], tags: set[str] | None = None, category: str | None = None) -> dict[str, Any]:
    tags = set(tags or tags_of(item))
    category = normalize_category(category or parent_primary_category(item))
    raw = int(item_num(item, "rare"))
    details = rarity_details_of(item)
    est = rarity_tier_estimate(raw, details)
    weight, note = rarity_role_weight(category, tags)
    converted = float(est["tierScore"]) * weight * RARITY_BASELINE_STRENGTH
    if not RARITY_BASELINE_ENABLED:
        converted = 0.0
    return {
        "rawRare": raw,
        "tierEstimate": est["tierEstimate"],
        "tierScore": round(float(est["tierScore"]), 2),
        "role": est["role"],
        "confidence": round(float(est["confidence"]), 2),
        "conversionCategory": category,
        "roleWeight": round(weight, 3),
        "strength": round(RARITY_BASELINE_STRENGTH, 3),
        "convertedPower": round(max(0.0, converted), 2),
        "note": note,
        "displayName": est.get("displayName"),
        "colorHex": est.get("colorHex"),
        "ordinal": est.get("ordinal"),
        "rarityDetails": details,
    }


def generic_modded_progression_signal(item: dict[str, Any], tags: set[str] | None = None, category: str | None = None, rarity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generic non-vanilla progression signal without per-mod material name tables.

    This deliberately does not claim a stage. It only says: the live item looks high-tier
    because of raw ModRarity/value/combat/tool/armor signals. The LLM still authors the result.
    """
    source_mod = str(item_field(item, "sourceMod", "Terraria") or "Terraria")
    if not source_mod or source_mod.lower() == "terraria":
        return {"score": 0.0, "confidence": 0.0, "reasons": []}
    tags = set(tags or tags_of(item))
    category = normalize_category(category or parent_primary_category(item))
    rarity = rarity or rarity_baseline_signal(item, tags, category)
    reasons: list[str] = ["non_vanilla_source"]
    score = 0.0
    conf = 0.35
    try:
        raw_rare = int(rarity.get("rawRare") or item_num(item, "rare", 0))
    except Exception:
        raw_rare = 0
    tier_score = float(rarity.get("tierScore") or 0.0)
    converted = float(rarity.get("convertedPower") or 0.0)
    if raw_rare > 11 or str(rarity.get("role") or "").startswith("unknown_modded"):
        score = max(score, converted, tier_score * (0.72 if category in {"material", "generic"} else 0.82))
        conf = max(conf, 0.52)
        reasons.append("modded_rarity")
    value = max(0.0, item_num(item, "value", 0))
    if value >= 50000:
        # Sell value is noisy, but it is one of the only generic progression signals for arbitrary mods.
        value_score = min(560.0, 80.0 + math.log1p(value / 50000.0) * 115.0)
        score = max(score, value_score)
        conf = max(conf, 0.46)
        reasons.append("high_value")
    dmg = item_num(item, "damage", 0)
    if dmg > 0:
        prof = source_weapon_profile(item)
        mech = min(620.0, math.sqrt(max(0.0, float(prof.get("effectiveDpsSignal") or 0.0))) * 13.5)
        score = max(score, mech)
        conf = max(conf, 0.58)
        reasons.append("combat_stats")
    tool = max(item_num(item, "pickPower", 0) * 1.35, item_num(item, "axePower", 0) * 7.0, item_num(item, "hammerPower", 0) * 1.25)
    if tool > 0:
        score = max(score, min(520.0, tool))
        conf = max(conf, 0.54)
        reasons.append("tool_stats")
    defense = item_num(item, "defense", 0)
    if defense > 0:
        score = max(score, min(520.0, defense * 9.0))
        conf = max(conf, 0.54)
        reasons.append("armor_stats")
    return {"score": round(max(0.0, score), 2), "confidence": round(min(0.78, conf), 2), "reasons": reasons, "sourceMod": source_mod, "rarity": rarity}



def known_item_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    if not KNOWLEDGE_ENABLED:
        return None
    items = ITEM_KNOWLEDGE.get("items") or {}
    candidates = set(wire_identity_names(item))
    name = knowledge_key(name_of(item))
    candidates.add(name)
    # Generated names often preserve the real parent after a prefix.
    candidates.add(re.sub(r"^(generated|infini|triple generated|triple compacted)\s+", "", name).strip())
    for cand in list(candidates):
        if cand in items:
            return dict(items[cand])
    # Also allow a normalized key without spaces for internal IDs from mods.
    compact_items = {knowledge_key(k).replace(" ", ""): v for k, v in items.items()}
    for cand in list(candidates):
        compact = cand.replace(" ", "")
        if compact in compact_items:
            return dict(compact_items[compact])
    for pattern in ITEM_KNOWLEDGE.get("patterns") or []:
        contains = [knowledge_key(x) for x in pattern.get("contains", [])]
        if contains and all(any(x in cand for cand in candidates) for x in contains):
            return dict(pattern)
    return None


def runtime_recipe_frame_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Runtime-safe recipe frame.

    Hand-authored mod recipe graphs were intentionally removed in v2.7.
    A future adapter may feed live tModLoader Recipe data here.
    Runtime archives should not include hand-scored training examples.
    """
    rf = entry.get("runtimeRecipeFrame") if isinstance(entry, dict) else None
    return dict(rf) if isinstance(rf, dict) else {}


def stat_signal_power(item: dict[str, Any]) -> float:
    return float(mechanic_signal_power(item).get("score") or 0)


def infer_item_card(item: dict[str, Any], canonical: dict[str, Any] | None = None) -> dict[str, Any]:
    gd = generated_data_of(item)
    item_knowledge_raw = dict_get_ci(gd, "itemKnowledge", {})
    if isinstance(item_knowledge_raw, dict):
        rc = dict_get_ci(item_knowledge_raw, "resultCard")
        if isinstance(rc, dict) and rc.get("powerScore") is not None:
            card = dict(rc)
            card.setdefault("name", name_of(item))
            card.setdefault("generatedDepth", generation_depth(item))
            card.setdefault("confidence", 0.72)
            card.setdefault("source", "generated_parent_card")
            return card

    tags = set(tags_of(item))
    entry = known_item_entry(item) or {}
    tags |= {str(t).lower() for t in entry.get("tags", []) if str(t).strip()}
    category = normalize_category(entry.get("category") or ("material" if "material" in tags else parent_primary_category(item)))
    stage = str(entry.get("stage") or entry.get("tier") or "unknown")
    tier = stage
    # Runtime uses tier defaults, mechanics, rarity baseline, and generated result cards.
    # Hand-authored per-item power labels must live outside the runtime archive.
    explicit_power = float(TIER_DEFAULT_POWER.get(tier, 0))
    signal = mechanic_signal_power(item)
    signal_power = float(signal.get("score") or 0)
    # If we have an exact knowledge card, do not let sell value alone override it too hard.
    # Real mechanics (damage/defense/tool power) can still raise the score, but a weird value field should not turn Wulfrum into superboss material.
    if entry and str(signal.get("basis", "")) == "value_baseline":
        signal_power = min(signal_power, explicit_power + 20.0)
    rarity_base = rarity_baseline_signal(item, tags, category)
    rarity_power = float(rarity_base.get("convertedPower") or 0)
    depth = generation_depth(item)
    # Generated depth is novelty, not pure power. Small boost only.
    # Known cards win, then mechanics, then rarity baseline. Rarity is approximate but meaningful.
    # If a generic name-pattern entry is weaker than a concrete ModRarity class (for example
    # Calamity BurnishedAuric/CosmicPurple), let the rarity class lift the tier label too.
    if rarity_power > explicit_power * 1.08 and str(rarity_base.get("role", "")).startswith(("calamity_rarity_class", "special_rarity_class")):
        tier = str(rarity_base.get("tierEstimate") or tier)
    power = max(explicit_power, signal_power, rarity_power) + min(14.0, depth * 2.5)
    if power <= 0:
        if "material" in tags or "block" in tags:
            power = max(8.0, rarity_power)
        elif int(item.get("damage") or 0) > 0:
            power = max(10.0, int(item.get("damage") or 0) * 1.05, rarity_power * 0.72)
        else:
            power = max(5.0, rarity_power * 0.65)
    if tier == "unknown":
        for t, default in sorted(TIER_DEFAULT_POWER.items(), key=lambda kv: kv[1], reverse=True):
            if power >= default * 0.92:
                tier = t
                break
        else:
            tier = "trash" if power < 8 else "early"
    confidence = 0.9 if entry else 0.48
    if signal_power > explicit_power and not entry:
        confidence = 0.66 if str(signal.get("basis", "")).startswith("mechanics") else 0.56
    if rarity_power > max(explicit_power, signal_power) and not entry:
        confidence = max(confidence, 0.58 if int(rarity_base.get("rawRare") or 0) <= 13 else 0.52)
    if depth:
        confidence = max(confidence, 0.62)
    return {
        "name": name_of(item),
        "identity": item_identity(item),
        "category": category,
        "tier": tier,
        "powerScore": round(power, 2),
        "confidence": round(min(0.98, confidence), 2),
        "sourceHint": str(entry.get("sourceHint") or ("generated parent" if depth else ("rarity baseline + mechanics/name/tags" if rarity_power > 0 else "inferred from mechanics/name/tags"))),
        "tags": sorted(tags),
        "generatedDepth": depth,
        "recipeFrame": runtime_recipe_frame_for_entry(entry),
        "signals": {
            "damage": int(item_num(item, "damage")),
            "rare": int(item_num(item, "rare")),
            "rarityDetails": rarity_details_of(item),
            "value": int(item_num(item, "value")),
            "pickPower": int(item_num(item, "pickPower")),
            "axePower": int(item_num(item, "axePower")),
            "hammerPower": int(item_num(item, "hammerPower")),
            "defense": int(item_num(item, "defense")),
            "healLife": int(item_num(item, "healLife")),
            "healMana": int(item_num(item, "healMana")),
            "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
            "internalName": str(item_field(item, "internalName", "")),
            "mechanicPower": signal,
            "rarityBaseline": rarity_base,
            "isMaterial": "material" in tags or category == "material",
            "isGenerated": depth > 0,
        },
    }


def build_item_knowledge(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any] | None = None, cb: dict[str, Any] | None = None) -> dict[str, Any]:
    cards = [infer_item_card(a, ca), infer_item_card(b, cb)]
    strongest = max(cards, key=lambda c: float(c.get("powerScore") or 0))
    material_cards = [c for c in cards if c.get("category") == "material" or c.get("signals", {}).get("isMaterial")]
    strongest_material = max(material_cards, key=lambda c: float(c.get("powerScore") or 0), default=None)
    tags = []
    for c in cards:
        tags.extend(c.get("tags") or [])
    return {
        "enabled": KNOWLEDGE_ENABLED,
        "parents": cards,
        "strongestTier": strongest.get("tier", "unknown"),
        "strongestPowerScore": strongest.get("powerScore", 0),
        "strongestSourceHint": strongest.get("sourceHint", ""),
        "strongestMaterialTier": (strongest_material or {}).get("tier", ""),
        "strongestMaterialPowerScore": (strongest_material or {}).get("powerScore", 0),
        "tagsFromKnowledge": sorted(set(str(t).lower() for t in tags)),
    }


def apply_item_knowledge(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    knowledge = build_item_knowledge(a, b, ca, cb)
    data["itemKnowledge"] = knowledge
    # v0.4.24 prompt validation slim: parent knowledge is validator/debug context.
    # Do not inject inferred parent tags into LLM-authored result tags in runtime authoring mode,
    # because that makes later VFX/category layers behave as if the code authored semantics.
    tags = set(str(t).lower() for t in data.get("tags", []))
    if not (LLM_RUNTIME_AUTHORING and runtime_plan(data)):
        tags |= set(knowledge.get("tagsFromKnowledge") or [])
    data["tags"] = sorted(tags)
    dbg = data.setdefault("debug", {})
    dbg["itemKnowledge"] = json.dumps(knowledge, ensure_ascii=False)
    dbg["itemKnowledgeTagMerge"] = "disabled_runtime_authoring" if (LLM_RUNTIME_AUTHORING and runtime_plan(data)) else "enabled_non_runtime_fallback"
    return data


def item_knowledge_power(data: dict[str, Any]) -> float:
    k = data.get("itemKnowledge") if isinstance(data.get("itemKnowledge"), dict) else {}
    try:
        return float(k.get("strongestPowerScore") or 0)
    except Exception:
        return 0.0

# -----------------------------------------------------------------------------
# Planner / resolver
# -----------------------------------------------------------------------------


class PlannerUnavailable(RuntimeError):
    """Raised when no authored LLM result is available for a real craft."""


class WorldScopeMissing(RuntimeError):
    """Raised when a gameplay craft is missing a real Terraria world id.

    InfiniCraft recipes are world-local discoveries: the same pair in the same
    world must resolve to the same item, while another world may discover a
    different result. Falling back to a silent global key would leak recipes
    between worlds and break that architecture.
    """


def normalize_world_id_from_payload(payload: dict[str, Any]) -> str:
    if "worldId" not in payload:
        raise WorldScopeMissing("missing worldId; InfiniCraft recipe cache is world-local and refuses global gameplay recipes")
    raw = payload.get("worldId")
    if raw is None:
        raise WorldScopeMissing("worldId is null; InfiniCraft recipe cache is world-local and refuses global gameplay recipes")
    world_id = str(raw).strip()
    if not world_id or world_id.lower() in {"global", "none", "null"}:
        raise WorldScopeMissing("invalid worldId; InfiniCraft recipe cache is world-local and refuses global gameplay recipes")
    return world_id



# =============================================================================
# NAV: GAMEPLAY_AND_ATTACK_PIPELINE
# =============================================================================







# DEV-only fallback base/tool/weapon plan builders live in dev_fallback.py.
# Normal generation enters via try_llm_plan() and runtime_authoring.py.





BAD_NAME_PATTERNS = [
    re.compile(r"^\s*infini(?:\s|$|[-_])", re.I),
    re.compile(r"^\s*generated(?:\s|$|[-_])", re.I),
    re.compile(r"^\s*combined(?:\s|$|[-_])", re.I),
    re.compile(r"\bhybrid\b", re.I),
]































# =============================================================================
# NAV: CATEGORY_AND_POLICY
# =============================================================================





# DEV-only accessory fallback builder lives in dev_fallback.py.















EFFECT_PRESENTATION = {
    "none": {"color": "white", "trail": "faint", "impact": "small_flash", "sound": "soft"},
    "dust": {"color": "white", "trail": "dust", "impact": "puff", "sound": "soft"},
    "electric": {"color": "cyan_yellow", "trail": "jagged_sparks", "impact": "electric_snap", "sound": "electric"},
    "slime": {"color": "green", "trail": "glob_droplets", "impact": "squish_burst", "sound": "slime"},
    "star": {"color": "white_gold", "trail": "sparkle", "impact": "starburst", "sound": "star"},
    "flame": {"color": "orange_red", "trail": "embers", "impact": "flame_pop", "sound": "fire"},
    "fire": {"color": "orange_red", "trail": "embers", "impact": "flame_pop", "sound": "fire"},
    "frost": {"color": "ice_blue", "trail": "snow_sparks", "impact": "ice_flash", "sound": "ice"},
    "leaf": {"color": "green_yellow", "trail": "leaf_specks", "impact": "petal_puff", "sound": "leaf"},
    "shadow": {"color": "purple_black", "trail": "dark_wisps", "impact": "shadow_flash", "sound": "shadow"},
    "poison": {"color": "toxic_green", "trail": "toxic_bubbles", "impact": "venom_splash", "sound": "poison"},
    "blood": {"color": "deep_red", "trail": "red_sparks", "impact": "cut_splatter", "sound": "cut"},
    "honey": {"color": "amber", "trail": "sticky_drops", "impact": "sticky_pop", "sound": "slime"},
    "sand": {"color": "sand_gold", "trail": "sand_grain", "impact": "sand_puff", "sound": "sand"},
    "heal": {"color": "green_pink", "trail": "soft_sparkle", "impact": "heal_pop", "sound": "heal"},
    "potion": {"color": "green_pink", "trail": "soft_sparkle", "impact": "potion_pop", "sound": "heal"},
    "holy": {"color": "white_gold", "trail": "sparkle", "impact": "soft_flash", "sound": "star"},
    "smoke": {"color": "gray", "trail": "smoke", "impact": "smoke_puff", "sound": "soft"},
    "lunar": {"color": "cyan_violet", "trail": "cosmic_sparkle", "impact": "lunar_burst", "sound": "star"},
    "crystal": {"color": "cyan_pink", "trail": "crystal_shards", "impact": "crystal_chime", "sound": "crystal"},
    "explosion": {"color": "orange_white", "trail": "smoke_embers", "impact": "explosion", "sound": "explosion"},
    "spectral": {"color": "pale_blue", "trail": "ghost_wisp", "impact": "spectral_flash", "sound": "shadow"},
    "mechanical": {"color": "steel_cyan", "trail": "metal_sparks", "impact": "metal_hit", "sound": "mechanical"},
}









LLM_RAW_TOKEN_MODE = env_str("INFINI_LLM_RAW_TOKEN_MODE", "compact").lower()
LLM_AMMO_REP_LIMIT = env_int("INFINI_LLM_AMMO_REP_LIMIT", 3)
# v0.4.51: LLM should see behavior words, not opaque vanilla aiStyle numbers.
# Keep numeric aiStyle internal/debug by default; expose only if explicitly requested.
LLM_INCLUDE_AISTYLE_RAW = env_bool("INFINI_LLM_INCLUDE_AISTYLE", False)
LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST = env_bool("INFINI_LLM_PROJECTILE_BEHAVIOR_DIGEST", True)

# Raw sections are still factual, but they should be compact: keep zeros/False because they
# are meaningful raw values, drop only null/empty strings/empty containers and duplicated
# sourceItem echo that is already present in itemRaw.
LLM_ITEM_RAW_KEYS = [
    "type", "name", "internalName", "sourceMod", "fullName",
    "damage", "damageClass", "damageClassFullName", "knockback", "crit",
    "useStyle", "useTime", "useAnimation", "reuseDelay", "autoReuse", "channel", "noMelee", "noUseGraphic", "useTurn",
    "rare", "rarityDetails", "value", "maxStack", "consumable", "material", "accessory", "defense",
    "headSlot", "bodySlot", "legSlot", "createTile", "createWall",
    "pickPower", "axePower", "hammerPower", "pick", "axe", "hammer",
    "healLife", "healMana", "manaCost", "buffType", "buffTime",
    "ammo", "useAmmo", "shoot", "shootSpeed", "fishingPole", "bait",
]
LLM_PROJECTILE_RAW_KEYS = [
    "source", "inventorySlot", "type", "internalName", "sourceMod", "fullName",
    "itemShootSpeed", "width", "height", "scale", "penetrate", "maxPenetrate", "timeLeft", "extraUpdates",
    "tileCollide", "ignoreWater", "friendly", "hostile", "arrow", "minion", "sentry", "minionSlots",
    "ownerHitCheck", "usesLocalNPCImmunity", "localNPCHitCooldown", "usesIDStaticNPCImmunity", "idStaticNPCHitCooldown",
    "stopsDealingDamageAfterPenetrateHits", "light", "alpha", "netImportant", "damageClass", "damageClassFullName",
    "framesRaw", "setsRaw", "fromGeneratedAttack", "engineMetrics", "unavailable",
]
LLM_AMMO_ITEM_KEYS = [
    "source", "inventorySlot", "type", "name", "internalName", "sourceMod", "fullName", "damage", "damageClass", "damageClassFullName",
    "ammo", "useAmmo", "shoot", "shootSpeed", "knockback", "rare", "value", "maxStack", "consumable", "material",
]




























# Runtime validator policy deliberately avoids per-item semantic exception tables.
# Parent tags may still exist as raw/debug/legacy category evidence elsewhere, but combat
# safety below is authored-field and engine-pressure based, not item-family routing.















































# =============================================================================
# NAV: LLM_PLAN_AND_REPAIR
# =============================================================================




# JSON object extraction/parsing lives in llm_json_tools.py. server.py re-exports
# the imported helpers for existing tests/tools that call server.parse_first_valid_llm_json.












_RESOLVED_LLM_MODEL: str | None = None




























# -----------------------------------------------------------------------------
# Validation / gameplay / visual
# -----------------------------------------------------------------------------






STAGE_PROFILES = [
    {"name": "wood", "minDamage": 5, "maxDamage": 12, "rarity": 0, "value": 50, "useTime": 30, "speed": 6.5, "pierce": 1, "mana": 3, "powerBudget": 0.65},
    {"name": "early", "minDamage": 8, "maxDamage": 18, "rarity": 0, "value": 100, "useTime": 28, "speed": 7.0, "pierce": 1, "mana": 4, "powerBudget": 0.85},
    {"name": "pre_boss", "minDamage": 13, "maxDamage": 26, "rarity": 1, "value": 250, "useTime": 26, "speed": 7.5, "pierce": 1, "mana": 5, "powerBudget": 1.05},
    {"name": "evil_boss", "minDamage": 20, "maxDamage": 38, "rarity": 2, "value": 700, "useTime": 25, "speed": 8.0, "pierce": 2, "mana": 6, "powerBudget": 1.25},
    {"name": "pre_hardmode_late", "minDamage": 32, "maxDamage": 58, "rarity": 3, "value": 1800, "useTime": 24, "speed": 8.5, "pierce": 2, "mana": 7, "powerBudget": 1.55},
    {"name": "hardmode_early", "minDamage": 48, "maxDamage": 82, "rarity": 4, "value": 4500, "useTime": 23, "speed": 9.0, "pierce": 2, "mana": 8, "powerBudget": 1.9},
    {"name": "mech", "minDamage": 70, "maxDamage": 112, "rarity": 5, "value": 9000, "useTime": 22, "speed": 9.5, "pierce": 3, "mana": 9, "powerBudget": 2.25},
    {"name": "plantera", "minDamage": 92, "maxDamage": 145, "rarity": 7, "value": 15000, "useTime": 21, "speed": 10.0, "pierce": 3, "mana": 10, "powerBudget": 2.7},
    {"name": "lunar", "minDamage": 130, "maxDamage": 210, "rarity": 9, "value": 24000, "useTime": 20, "speed": 10.5, "pierce": 4, "mana": 12, "powerBudget": 3.25},
    {"name": "endgame", "minDamage": 170, "maxDamage": 280, "rarity": 10, "value": 40000, "useTime": 18, "speed": 11.5, "pierce": 5, "mana": 14, "powerBudget": 4.0},
]






















MOVEMENT_CODE = {
    "straight": 0, "slow_homing": 1, "gravity_arc": 2, "drift": 3, "orbit": 4,
    "boomerang": 5, "bounce": 6, "sine_homing": 7, "phase": 8, "accelerate": 9,
    "spiral": 10, "vortex_orb": 11, "blackhole_pull": 12, "proximity_missile": 13,
    "returning_glaive": 14, "expanding_wave": 15,
    "flail_tether": 16, "yoyo_hover": 17, "whip_lash": 18,
}
MOVEMENT_ALIASES = {
    "rain": "gravity_arc",
    "fall": "gravity_arc",
    "falling": "gravity_arc",
    "falling_projectile": "gravity_arc",
    "projectile_rain": "gravity_arc",
    "starfall": "gravity_arc",
    "skyfall": "gravity_arc",
    "meteor": "gravity_arc",
    "arc": "gravity_arc",
    "lob": "gravity_arc",
    "lobbed": "gravity_arc",
    "grenade_arc": "gravity_arc",
    "homing": "slow_homing",
    "seeking": "slow_homing",
    "guided": "slow_homing",
    "tracking": "slow_homing",
    "return": "returning_glaive",
    "returning": "returning_glaive",
    "returning_throw": "returning_glaive",
    "glaive_return": "returning_glaive",
    "chakram": "boomerang",
    "boomerang_return": "boomerang",
    "wave": "expanding_wave",
    "shockwave": "expanding_wave",
    "ring": "expanding_wave",
    "beam": "phase",
    "laser": "phase",
    "ray": "phase",
    "hitscan": "phase",
    "missile": "proximity_missile",
    "rocket": "proximity_missile",
    "orb": "vortex_orb",
    "flail": "flail_tether",
    "chain_flail": "flail_tether",
    "mace": "flail_tether",
    "anchor": "flail_tether",
    "yoyo": "yoyo_hover",
    "yo_yo": "yoyo_hover",
    "whip": "whip_lash",
    "lash": "whip_lash",
}
DELIVERY_VALUES = {"none", "swing", "thrust", "spear", "shoot", "cast", "throw", "summon", "flail", "yoyo", "whip"}
RUNTIME_FAMILY_VALUES = {"none", "swing", "thrust", "returning", "flail", "yoyo", "whip", "shoot", "cast", "throw", "summon"}
DELIVERY_ALIASES = {
    "slash": "swing", "melee_arc": "swing", "blade_arc": "swing", "sword": "swing", "axe": "swing", "hammer": "swing", "club": "swing",
    "stab": "thrust", "rapier": "thrust", "shortsword": "thrust", "short_sword": "thrust", "held_thrust": "thrust", "spear_thrust": "thrust",
    "polearm": "thrust", "lance": "thrust", "pike": "thrust", "trident": "thrust", "halberd": "thrust", "naginata": "thrust",
    "ranged": "shoot", "bow": "shoot", "repeater": "shoot", "gun": "shoot", "launcher": "shoot", "crossbow": "shoot", "blowgun": "shoot",
    "magic": "cast", "spell": "cast", "staff": "cast", "wand": "cast", "rod": "cast", "book": "cast", "spellbook": "cast",
    "thrown": "throw", "knife": "throw", "dart": "throw", "grenade": "throw",
    "boomerang": "throw", "chakram": "throw", "glaive_throw": "throw", "returning_throw": "throw",
    "flail": "flail", "chain_flail": "flail", "ball_and_chain": "flail", "mace": "flail", "anchor": "flail",
    "yoyo": "yoyo", "yo_yo": "yoyo",
    "whip": "whip", "lash": "whip",
    "minion": "summon", "sentry": "summon", "summon_projectile": "summon",
}
EFFECT_ALIASES = {
    "fire": "flame", "burn": "flame", "ember": "flame", "lava": "flame", "magma": "flame",
    "ice": "frost", "cold": "frost", "snow": "frost", "frostburn": "frost",
    "lightning": "electric", "shock": "electric", "thunder": "electric", "storm": "electric",
    "venom": "poison", "toxic": "poison", "acid": "poison", "ichor": "poison",
    "dark": "shadow", "void": "shadow", "grave": "shadow", "shadowflame": "shadow",
    "nature": "leaf", "plant": "leaf", "spore": "leaf",
    "water": "slime", "goo": "slime", "gel": "slime",
    "radiant": "holy", "light": "holy", "solar": "holy",
    "smog": "smoke", "ash": "smoke",
}
ONHIT_ALIASES = {
    "fire": "burn", "on_fire": "burn", "ignite": "burn",
    "ice": "frostburn", "freeze": "frostburn", "chill": "frostburn",
    "venom": "poison", "toxic": "poison", "acid": "poison",
    "electric": "lightning_arc", "electrified": "lightning_arc", "shock": "lightning_arc", "zap": "lightning_arc",
    "blood": "bleed", "bleeding": "bleed",
    "explode": "burst", "explosion": "burst", "nova": "burst",
    "fragment": "split", "fragments": "split", "shards": "split",
    "star": "starburst", "stars": "starburst", "star_rain": "starfall", "falling_stars": "starfall", "star_wrath": "starfall", "sky_stars": "starfall",
    "life_steal": "lifesteal",
}
EFFECT_CODE = {
    "none": 0, "dust": 0, "electric": 1, "slime": 2, "star": 3, "flame": 4, "frost": 5,
    "leaf": 6, "shadow": 7, "poison": 8, "blood": 9, "honey": 10, "sand": 11, "lunar": 12, "heal": 13, "holy": 14, "smoke": 15,
}
ONHIT_CODE = {
    "none": 0, "burst": 1, "split": 2, "chain": 3, "burn": 4, "frostburn": 5,
    "poison": 6, "shadowflame": 7, "starburst": 8, "bleed": 9, "aura_pulse": 10,
    "spore_cloud": 11, "mini_missiles": 12, "vortex_spawn": 13, "blackhole": 14,
    "radial_beams": 15, "lightning_arc": 16, "lifesteal": 17, "heal": 17, "starfall": 18,
}






















LLM_REQUIRED_GENOME_FIELDS = [
    "delivery", "movement", "effect", "onHit",
    "useTimeTicks", "shotCount", "pierce", "aoeRadiusTiles",
    "lifetimeTicks", "rangeTiles", "reliability", "selfLockTicks", "missPunish",
]

LLM_OPTIONAL_GENOME_DEFAULTS = {
    "homingStrength": 0.0,
    "extraUpdates": 0,
    "spreadRadians": 0.0,
    "speed": 8.0,
    "splitCount": 0,
    "chainCount": 0,
    "trailLength": 0,
    "burstDustCap": 0,
}

LLM_NUMERIC_GENOME_LIMITS = {
    "useTimeTicks": (10.0, 150.0),
    "shotCount": (1.0, 8.0),
    "pierce": (-1.0, 10.0),
    "aoeRadiusTiles": (0.0, 10.0),
    "homingStrength": (0.0, 1.0),
    "lifetimeTicks": (25.0, 900.0),
    "extraUpdates": (0.0, 3.0),
    "rangeTiles": (4.0, 120.0),
    "reliability": (0.45, 1.25),
    "selfLockTicks": (0.0, 120.0),
    "missPunish": (0.0, 1.0),
    "spreadRadians": (0.0, 0.75),
    "speed": (3.0, 18.0),
    "splitCount": (0.0, 8.0),
    "chainCount": (0.0, 6.0),
    "trailLength": (0.0, 24.0),
    "burstDustCap": (0.0, 40.0),
}

























































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

def generated_parent_summary_from_data(data: dict[str, Any]) -> dict[str, Any]:
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    accessory = data.get("accessory") if isinstance(data.get("accessory"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    effects: list[str] = []
    for value in [attack.get("effect"), attack.get("onHit"), attack.get("movement"), attack.get("trailStyle"), attack.get("impactStyle")]:
        text = str(value or "").strip()
        if text and text.lower() not in {"none", "dust", "small_flash", "straight"}:
            effects.append(text[:64])
    gb = gameplay.get("generatedBuff") if isinstance(gameplay.get("generatedBuff"), dict) else {}
    if gb:
        if float(gb.get("miningSpeedMultiplier") or 1) != 1:
            effects.append("generated buff: mining speed")
        if float(gb.get("emitLightStrength") or 0) > 0:
            effects.append("generated buff: light")
        if int(gb.get("oreSenseRadiusTiles") or 0) > 0:
            effects.append("generated buff: ore sense")
        if float(gb.get("movementSpeed") or 0) != 0 or float(gb.get("jumpBoost") or 0) > 0:
            effects.append("generated buff: mobility stats")
        if int(gb.get("manaRegen") or 0) > 0 or int(gb.get("lifeRegen") or 0) > 0:
            effects.append("generated buff: regeneration")
    mobility = str(gameplay.get("mobilityMode") or "").strip()
    if mobility:
        effects.append("mobility: " + mobility[:48])
    if int(gameplay.get("extractinatorOutputItemType") or 0) > 0:
        effects.append("extractinator output")
    if int(gameplay.get("consumeChancePercent") or 100) < 100:
        effects.append("custom consume chance")
    runtime_state = gameplay.get("runtimeState") if isinstance(gameplay.get("runtimeState"), dict) else {}
    if runtime_state.get("stateMeters"):
        effects.append("runtime state: meters")
    if runtime_state.get("triggeredActions"):
        effects.append("runtime state: triggers")
    if gameplay.get("rejectedEngineCalls"):
        effects.append("rejected unsupported calls")
    try:
        vanilla_hitbox_damage = (
            int(float(gameplay.get("damage") or 0)) > 0
            and int(float(gameplay.get("useStyle") or 0)) > 0
            and normalize_category(data.get("category") or gameplay.get("kind") or "generic") not in {"ammo", "accessory", "material", "furniture"}
            and not (bool(attack.get("enabled")) and bool(attack.get("disableItemMeleeHitbox")))
        )
    except Exception:
        vanilla_hitbox_damage = False
    if vanilla_hitbox_damage and not attack.get("enabled"):
        effects.append("vanilla item/tool hitbox")
    if accessory.get("enabled"):
        acc_parts = []
        if int(accessory.get("defense") or 0) > 0: acc_parts.append("defense")
        if float(accessory.get("movementSpeed") or 0) > 0 or float(accessory.get("jumpSpeed") or 0) > 0: acc_parts.append("mobility")
        if float(accessory.get("genericDamage") or 0) > 0 or float(accessory.get("meleeDamage") or 0) > 0 or float(accessory.get("rangedDamage") or 0) > 0 or float(accessory.get("magicDamage") or 0) > 0 or float(accessory.get("summonDamage") or 0) > 0: acc_parts.append("damage")
        if float(accessory.get("lightStrength") or 0) > 0: acc_parts.append("light")
        if int(accessory.get("minionSlots") or 0) > 0: acc_parts.append("minion slots")
        effects.append("accessory" + (": " + ", ".join(acc_parts[:4]) if acc_parts else ""))
    return {
        "name": str(data.get("name") or "")[:80],
        "fantasy": compact_visual_words(concept.get("fantasy") or data.get("tooltip") or data.get("name"), 180),
        "category": normalize_category(data.get("category") or gameplay.get("kind") or "generic"),
        "damageClass": str(gameplay.get("damageClass") or "generic")[:32],
        "runtime": (
            str(attack.get("runtimeFamily") or "")[:32]
            if attack.get("enabled")
            else "vanilla_item_hitbox" if vanilla_hitbox_damage
            else "none"
        ),
        "customAttackEnabled": bool(attack.get("enabled")),
        "vanillaItemHitboxDamage": bool(vanilla_hitbox_damage),
        "visualIdentity": compact_visual_words(visual.get("imagePrompt") or concept.get("visualIdentity") or data.get("name"), 180),
        "notableEffects": list(dict.fromkeys(effects))[:8],
    }


def attach_generated_parent_summary(data: dict[str, Any]) -> dict[str, Any]:
    data["generatedParentSummary"] = generated_parent_summary_from_data(data)
    data.setdefault("debug", {})["generatedParentSummary"] = json.dumps(data["generatedParentSummary"], ensure_ascii=False)
    return data

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



def _is_client_disconnect(exc: BaseException) -> bool:
    """Client closed the HTTP socket while we were writing a response.

    Common during GUI health checks/browser refreshes. It is not a generator crash.
    Windows often reports this as WinError 10053/10054.
    """
    if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        return True
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) in {10053, 10054}:
        return True
    return False


def _ascii_reason(value: Any, limit: int = 160) -> str:
    # HTTP status reason is latin-1 in BaseHTTPRequestHandler. Never pass repr(e)
    # with localized OS text there; send JSON body instead.
    text = str(value or "error").replace("\r", " ").replace("\n", " ").strip()
    text = text.encode("ascii", "backslashreplace").decode("ascii")
    return text[:limit] or "error"




def _combine_failure_http_response(error: BaseException | str, failure: dict[str, Any]) -> tuple[int, str, bool, str]:
    """Classify a failed /combine into transport-visible HTTP semantics.

    404 is reserved for cache-only misses. Authored/LLM output failures are
    422, visual delivery dependency failures are 424, and generic planner
    availability remains 424. `retryable` means the user may manually craft
    again; it does not mean C# should cache-poll the same failed attempt.
    """
    stage = str((failure or {}).get("stage") or "").lower()
    failure_error = str((failure or {}).get("error") or "")
    message = f"{error} {failure_error}".lower()

    if "09b_visual_delivery_gate" in stage or ("visual" in stage and any(token in message for token in ("asset", "sprite", "delivery"))):
        return 424, "visual_dependency_failed", True, "visual asset generation/delivery did not produce a deliverable item sprite"

    schema_stage = any(token in stage for token in ("schema", "validate", "repair"))
    llm_shape_error = any(token in message for token in (
        "runtimeplan failed",
        "engine-call validation",
        "lacks set_item_stats",
        "invalid runtime",
        "schema",
        "validation",
        "json",
    ))
    if schema_stage or llm_shape_error:
        return 422, "llm_output_invalid", True, "LLM returned an invalid/unsupported item plan after repair attempts"

    if "01_author_llm_plan" in stage or "planner unavailable" in message or "llm planner unavailable" in message:
        return 424, "planner_unavailable", True, "LLM planner did not return a usable item plan"

    return 424, "combine_failed", True, "combine pipeline failed before a deliverable recipe was committed"


def _combine_failure_player_message(status: int, code: str, message: str, failure: dict[str, Any], *, retryable: bool) -> str:
    if code == "llm_output_invalid":
        return "Generation failed: LLM item plan was invalid after repair. Items were returned; try crafting again."
    if code == "visual_dependency_failed":
        return "Generation failed: required visual asset was not deliverable. Items were returned; try again."
    if code == "planner_unavailable":
        return "Generation failed: LLM planner did not return a usable item. Items were returned; try again."
    if code == "generator_busy":
        return "Generator is busy. Items were returned; try again shortly."
    if status == 428:
        return "Generation failed: world id was missing. Items were returned."
    if retryable:
        return "Generation failed before a recipe was committed. Items were returned; try crafting again."
    return "Generation failed. Items were returned."


def _combine_failure_payload(status: int, code: str, message: str, failure: dict[str, Any], *, retryable: bool) -> dict[str, Any]:
    player_message = _combine_failure_player_message(status, code, message, failure, retryable=retryable)
    return {
        "ok": False,
        "status": code,
        "error": code,
        "message": str(message or code),
        "playerMessage": player_message,
        "developerHint": "No recipe was committed; do not cache-poll this attempt. Manual regenerate is allowed when retryable=true.",
        "version": APP_VERSION,
        "httpStatus": int(status),
        "retryable": bool(retryable),
        "cacheRecoveryAllowed": False,
        "manualRegenerateAllowed": bool(retryable),
        "lastFailure": failure or {},
    }


def _health_payload() -> dict[str, Any]:
    visual_director_configured = bool(VISUAL_DIRECTOR_LLM)
    visual_director_active = bool(USE_LLM and VISUAL_DIRECTOR_LLM)
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
        "contractVersions": contract_versions_payload(),
        "tmodloaderGreyZoneNotes": TMODLOADER_GREY_ZONE_NOTES,
        "imageBackend": IMAGE_BACKEND,
        "visualAssetMode": VISUAL_ASSET_MODE,
        "visualDirectorLLM": VISUAL_DIRECTOR_LLM,
        "visualDirectorLLMConfigured": visual_director_configured,
        "visualDirectorLLMActive": visual_director_active,
        "vfxLlmDirectorConfigured": vfx_llm_director_configured,
        "vfxLlmDirectorActive": vfx_llm_director_active,
        "visualPipelineProfile": VISUAL_PIPELINE_PROFILE,
        "visualGenerationTimeout": VISUAL_GENERATION_TIMEOUT,
        "visualRequireItemSprite": VISUAL_REQUIRE_ITEM_SPRITE,
        "visualRequireZImageBackend": VISUAL_REQUIRE_ZIMAGE_BACKEND,
        "zImagePromptContract": ZIMAGE_PROMPT_CONTRACT,
        "zImagePositiveOnly": ZIMAGE_POSITIVE_ONLY,
        "patternLibraryCards": PATTERN_LIBRARY_CARDS,
        "patternRepairAttempts": PATTERN_REPAIR_ATTEMPTS,
        "vfxSelector": VFX_SELECTOR_ENABLED,
        "vfxRecipeCount": len(get_vfx_recipes()),
        "vfxMacroCount": len(VFX_SLOT_MACROS),
        "vfxSelectorTop": VFX_SELECTOR_TOP,
        "vfxHintWeight": VFX_SELECTOR_HINT_WEIGHT,
        "vfxParentEffectInheritance": VFX_PARENT_EFFECT_INHERITANCE,
        "vfxParentEffectWeight": VFX_PARENT_EFFECT_WEIGHT,
        "vfxRenderQuality": VFX_RENDER_QUALITY,
        "vfxEmergencyCaps": {
            "maxParticlesPerTick": VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
            "maxParticlesTotal": VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
            "maxDrawCalls": VFX_EMERGENCY_MAX_DRAW_CALLS,
        },
        "removeBg": REMOVE_BG,
        "requirePillow": REQUIRE_PILLOW,
        "pillowAvailable": Image is not None,
        "bgRemoveMode": BG_REMOVE_MODE,
        "bgColor": BG_COLOR,
        "a1111Size": [A1111_WIDTH, A1111_HEIGHT],
        "comfyui": {
            "url": COMFYUI_URL,
            "workflow": str(resolve_comfyui_workflow_path() or COMFYUI_WORKFLOW),
            "checkpoint": COMFYUI_CHECKPOINT,
            "lora": COMFYUI_LORA_NAME,
            "size": [COMFYUI_WIDTH, COMFYUI_HEIGHT],
            "steps": COMFYUI_STEPS,
            "cfg": COMFYUI_CFG,
            "sampler": COMFYUI_SAMPLER,
            "scheduler": COMFYUI_SCHEDULER,
        },
        "sdcpp": {
            "mode": "server",
            "serverExe": SDCPP_SERVER_EXE,
            "model": SDCPP_MODEL,
            "vae": SDCPP_VAE,
            "llm": SDCPP_LLM,
            "commandMode": SDCPP_SERVER_COMMAND_MODE,
            "commandTemplate": SDCPP_SERVER_COMMAND_TEMPLATE,
            "templateRepair": sdcpp_repair_command_template(SDCPP_SERVER_COMMAND_TEMPLATE),
            "manualExtraArgs": SDCPP_SERVER_EXTRA_ARGS,
            "effectiveExtraArgs": sdcpp_effective_extra_args(),
            "serverConfigured": sdcpp_server_is_configured(),
            "serverUrl": SDCPP_SERVER_URL,
            "serverAutostart": SDCPP_SERVER_AUTOSTART,
            "serverAlive": sdcpp_server_is_alive(),
            "showConsole": SDCPP_SERVER_SHOW_CONSOLE,
            "logFile": SDCPP_SERVER_STATE.last_log_file or SDCPP_SERVER_LOG_FILE,
            "lastCommand": SDCPP_SERVER_STATE.last_command or _stringify_cmd(build_sdcpp_server_command()[0]),
            "lastStartError": SDCPP_SERVER_STATE.last_start_error,
            "lastExit": SDCPP_SERVER_STATE.last_exit,
            "size": [SDCPP_WIDTH, SDCPP_HEIGHT],
            "steps": SDCPP_STEPS,
            "cfg": SDCPP_CFG,
            "sampler": SDCPP_SAMPLER,
            "timeout": SDCPP_TIMEOUT,
            "serverTimeout": SDCPP_SERVER_REQUEST_TIMEOUT,
        },
        "imageVariants": GENERATE_VARIANTS,
        "spriteRetries": SPRITE_RETRIES,
        "spriteValidation": {
            "minBboxRatio": SPRITE_MIN_BBOX_RATIO,
            "maxBboxRatio": SPRITE_MAX_BBOX_RATIO,
            "minOpaquePct": SPRITE_MIN_OPAQUE_PCT,
            "maxOpaquePct": SPRITE_MAX_OPAQUE_PCT,
        },
        "deterministicDevFallback": ALLOW_DETERMINISTIC_DEV_FALLBACK,
        "lastCombineFailure": last_combine_failure_summary(),
        "worldRecipesDir": str(WORLD_RECIPES_DIR),
        "recipeCacheScope": "world",
        "recipeStorage": "world_recipes_files",
        "requiresWorldId": True,
        "recipeIdentityVersion": RECIPE_IDENTITY_VERSION,
        "assetSync": {"endpoint": "/get_asset", "publicBaseUrl": ASSET_PUBLIC_BASE_URL, "spriteDir": str(SPRITE_DIR)},
        "multiplayer": _multiplayer_connect_info(),
    }


def _last_combine_failure_payload() -> dict[str, Any]:
    if LAST_COMBINE_FAILURE:
        return LAST_COMBINE_FAILURE
    if LAST_COMBINE_FAILURE_FILE.exists():
        return json.loads(LAST_COMBINE_FAILURE_FILE.read_text(encoding="utf-8"))
    return {"ok": True, "version": APP_VERSION, "lastFailure": None}


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
        last_combine_failure_payload=_last_combine_failure_payload,
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


# Extracted pipeline modules use explicit imports; server.py stays as HTTP shell/wiring.


class Handler(BaseHTTPRequestHandler):
    server_version = f"InfiniCrafterLocal/{APP_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:
        try:
            if _utility_routes().handle_get(self, self.path):
                return
            if self.path.startswith("/debug/vfx"):
                if _vfx_debug_routes().handle_get(self, self.path):
                    return
            self.send_error(404)
        except Exception as e:
            if _is_client_disconnect(e):
                log_event("debug", "client disconnected during GET response", {"path": self.path, "error": repr(e)})
                return
            log_event("error", "GET request failed", {"path": self.path, "error": repr(e), "trace": traceback.format_exc()})
            self.json_error(500, "internal_error", repr(e))

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body or "{}")
            if self.path.startswith("/debug/vfx"):
                if _vfx_debug_routes().handle_post(self, self.path, payload):
                    return
            if self.path.startswith("/combine"):
                combine_endpoint.handle_combine_request(
                    payload,
                    app_version=APP_VERSION,
                    combine_cache_lookup=combine_cache_lookup,
                    sanitize_recipe_for_delivery=sanitize_recipe_for_delivery,
                    combine=combine,
                    trace_event=trace_event,
                    json=self.json,
                    json_status=self.json_status,
                    cache_lookup_passthrough_errors=(WorldScopeMissing,),
                )
                return
            self.send_error(404)
        except WorldScopeMissing as e:
            if _is_client_disconnect(e):
                return
            log_event("warn", "craft failed: world scope missing", {"path": self.path, "error": str(e)})
            self.json_error(428, "world_id_required", str(e))
        except VisualDeliveryBlocked as e:
            if _is_client_disconnect(e):
                return
            failure = last_combine_failure_summary()
            status, code, retryable, friendly = _combine_failure_http_response(e, failure)
            log_event("warn", "craft failed: visual delivery blocked", {
                "path": self.path,
                "httpStatus": status,
                "errorCode": code,
                "error": str(e),
                "lastFailure": failure,
            })
            self.json_status(status, _combine_failure_payload(status, code, friendly, failure, retryable=retryable))
        except PlannerUnavailable as e:
            if _is_client_disconnect(e):
                return
            failure = last_combine_failure_summary()
            status, code, retryable, friendly = _combine_failure_http_response(e, failure)
            log_event("warn", "craft failed: structured combine failure", {
                "path": self.path,
                "httpStatus": status,
                "errorCode": code,
                "error": str(e),
                "lastFailure": failure,
            })
            self.json_status(status, _combine_failure_payload(status, code, friendly, failure, retryable=retryable))
        except Exception as e:
            if _is_client_disconnect(e):
                log_event("debug", "client disconnected during POST response", {"path": self.path, "error": repr(e)})
                return
            log_event("error", "request failed", {"path": self.path, "error": repr(e), "trace": traceback.format_exc()})
            self.json_error(500, "internal_error", repr(e))

    def json(self, obj: Any) -> None:
        self.json_status(200, obj)

    def json_status(self, status: int, obj: Any) -> None:
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            if _is_client_disconnect(e):
                log_event("debug", "client disconnected while writing JSON response", {"path": self.path, "status": status, "error": repr(e)})
                return
            raise

    def json_error(self, status: int, code: str, message: str = "") -> None:
        self.json_status(status, {"ok": False, "error": str(code or "error"), "message": str(message or ""), "version": APP_VERSION})

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        # BaseHTTPRequestHandler.send_error puts message into the HTTP reason phrase,
        # which must be latin-1 and can explode on Russian Windows error text.
        try:
            self.json_error(int(code), f"http_{int(code)}", message or explain or "")
        except Exception as e:
            if _is_client_disconnect(e):
                return
            super().send_error(code, _ascii_reason(message or explain or "error"), None)


def main() -> None:
    if REQUIRE_PILLOW and Image is None and env_str("INFINI_IMAGE_BACKEND", IMAGE_BACKEND).lower() != "off":
        raise SystemExit("Pillow is required for InfiniCrafterLocal visual generation/postprocess. Run 02_INSTALL_LOCAL_GENERATOR.bat. Import error: " + PILLOW_IMPORT_ERROR)
    host = env_str("INFINI_HOST", "127.0.0.1")
    port = env_int("INFINI_PORT", 5055)
    print(f"InfiniCrafterLocal v{APP_VERSION} listening on http://{host}:{port}")
    print(f"LLM={USE_LLM} provider={active_llm_provider()} model={resolve_llm_model() if USE_LLM else '<off>'} deterministicDevFallback={ALLOW_DETERMINISTIC_DEV_FALLBACK} imageBackend={IMAGE_BACKEND} worldRecipes={WORLD_RECIPES_DIR}")
    if IMAGE_BACKEND in {"sdcpp", "stablediffusioncpp", "stable-diffusion.cpp", "stable_diffusion_cpp"}:
        print(f"stable-diffusion.cpp server={SDCPP_SERVER_URL} autostart={SDCPP_SERVER_AUTOSTART} exe={SDCPP_SERVER_EXE or '<external>'} model={SDCPP_MODEL or '<external>'} steps={SDCPP_STEPS} cfg={SDCPP_CFG} size={SDCPP_WIDTH}x{SDCPP_HEIGHT}")
    if USE_LLM:
        print("Tip: set INFINI_LLM_PROVIDER=openrouter + INFINI_OPENROUTER_API_KEY + INFINI_OPENROUTER_MODEL to use OpenRouter instead of LM Studio.")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
