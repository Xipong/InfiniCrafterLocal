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
    ROOT,
    RECIPE_IDENTITY_VERSION,
    DATA_DIR,
    CONFIG_PATH,
    CACHE_DIR,
    SPRITE_DIR,
    WORLD_RECIPES_DIR,
    TERRARIA_PORT,
    ASSET_PUBLIC_BASE_URL,
)
from infini_local.web.server_services import (
    env_bool,
    env_float,
    env_int,
    env_str,
    env_first,
    env_path,
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
    HARD_TAGS,
    VISUAL_SYNONYMS,
    knowledge_key,
    wire_identity_names,
    ATTACK_PATTERN_IDS,
    attack_pattern_contract_for_llm,
    normalize_attack_pattern,
    pattern_card,
    resolve_attack_pattern,
    select_pattern_cards,
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
    TMODLOADER_GREY_ZONE_NOTES,
    build_contract_versions,
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
    extract_json,
    json_object_candidates,
    parse_first_valid_llm_json,
    world_storage,
    sdcpp_backend,
    sdcpp_service,
    failure_state,
    asset_sync_service,
    combine_endpoint,
    runtime_dump_service,
    trace_dashboard,
    build_trace_snapshot,
    render_trace_snapshot_html,
    VfxDebugRoutes,
    ServerUtilityRoutes,
    visual_asset_pipeline,
    network_info_service,
    compact_zimage_asset_prompt,
    sanitize_image_prompt_background,
    sanitize_projectile_prompt_multiplicity,
    sanitize_visual_palette,
    sprite_status_from_raw_path,
    strip_conflicting_sprite_prompt_bits,
    _visual_palette_entry_is_chroma_key_noise,
    zimage_palette_sentence,
    zimage_pe_clean_text,
    zimage_text_policy_sentence,
    name_of,
    slug,
    stable_hash,
    item_identity,
    generated_data_of,
    fingerprint_of,
    item_field,
    item_num,
    item_bool,
    _world_recipe_key,
    combine_pipeline,
    llm_authoring_pipeline,
    parent_context_pipeline,
    visual_generation_pipeline,
    image_backend_pipeline,
    sprite_processing_pipeline,
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
    PALETTES,
    BAD_NAME_PATTERNS,
    EFFECT_PRESENTATION,
    LLM_ITEM_RAW_KEYS,
    LLM_PROJECTILE_RAW_KEYS,
    LLM_AMMO_ITEM_KEYS,
    _RESOLVED_LLM_MODEL,
    STAGE_PROFILES,
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
    behavior_cost_multiplier,
    clamp_float,
    dict_get_ci,
    estimate_engine_metrics,
    sanitize_genome_engine,
    attach_generated_parent_summary,
    generated_parent_summary_from_data,
    _ascii_reason,
    _combine_failure_http_response,
    _combine_failure_payload,
    _is_client_disconnect,
)
from infini_local.web.server_handler import build_handler

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

# Item power and knowledge helpers are owned by pipelines/item_power_knowledge.py.


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
        image_backend=IMAGE_BACKEND,
        visual_asset_mode=VISUAL_ASSET_MODE,
        visual_director_llm=VISUAL_DIRECTOR_LLM,
        vfx_llm_director_enabled=VFX_LLM_DIRECTOR_ENABLED,
        openrouter_model=OPENROUTER_MODEL,
        openai_compat_model=OPENAI_COMPAT_MODEL,
        lmstudio_model=LMSTUDIO_MODEL,
        trace_prompts_enabled=TRACE_PROMPTS_ENABLED,
        trace_max_prompt_chars=TRACE_MAX_PROMPT_CHARS,
        trace_events_tail=TRACE_EVENTS_TAIL,
        prompt_trace_file=PROMPT_TRACE_FILE,
        trace_file=TRACE_FILE,
        last_combine_failure_file=LAST_COMBINE_FAILURE_FILE,
        last_combine_failure_summary=last_combine_failure_summary,
        active_llm_provider=active_llm_provider,
        llm_auth_snapshot=llm_auth_snapshot,
        contract_versions_payload=contract_versions_payload,
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


class PlannerUnavailable(RuntimeError):
    """Raised when no authored LLM result is available for a real craft."""


# =============================================================================
# NAV: GAMEPLAY_AND_ATTACK_PIPELINE
# =============================================================================


# DEV-only fallback base/tool/weapon plan builders live in dev_fallback.py.
# Normal generation enters via try_llm_plan() and the runtime_authoring package.


# =============================================================================
# NAV: CATEGORY_AND_POLICY
# =============================================================================


# DEV-only accessory fallback builder lives in dev_fallback.py.


LLM_RAW_TOKEN_MODE = env_str("INFINI_LLM_RAW_TOKEN_MODE", "compact").lower()
LLM_AMMO_REP_LIMIT = env_int("INFINI_LLM_AMMO_REP_LIMIT", 3)
# v0.4.51: LLM should see behavior words, not opaque vanilla aiStyle numbers.
# Keep numeric aiStyle internal/debug by default; expose only if explicitly requested.
LLM_INCLUDE_AISTYLE_RAW = env_bool("INFINI_LLM_INCLUDE_AISTYLE", False)
LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST = env_bool("INFINI_LLM_PROJECTILE_BEHAVIOR_DIGEST", True)

# Raw sections are still factual, but they should be compact: keep zeros/False because they
# are meaningful raw values, drop only null/empty strings/empty containers and duplicated
# sourceItem echo that is already present in itemRaw.


# Runtime validator policy deliberately avoids per-item semantic exception tables.
# Parent tags may still exist as raw/debug/legacy category evidence elsewhere, but combat
# safety below is authored-field and engine-pressure based, not item-family routing.


# =============================================================================
# NAV: LLM_PLAN_AND_REPAIR
# =============================================================================


# JSON object extraction/parsing lives in llm_json_tools.py. server.py re-exports
# the imported helpers for existing tests/tools that call server.parse_first_valid_llm_json.


# -----------------------------------------------------------------------------
# Validation / gameplay / visual
# -----------------------------------------------------------------------------


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
# The VFX manifest package owns generation-time VFX assembly.


# =============================================================================
# NAV: FINAL_NORMALIZE_AND_HTTP
# =============================================================================


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
    last_combine_failure_summary=last_combine_failure_summary,
    combine_failure_http_response=_combine_failure_http_response,
    combine_failure_payload=_combine_failure_payload,
    ascii_reason=_ascii_reason,
)


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
