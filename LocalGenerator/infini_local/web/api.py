from __future__ import annotations

# AGENT MAP: canonical Python API for diagnostics, tests, and tooling that need
# cross-module generator services without starting the HTTP server.

from infini_local.core.llm_json_tools import (
    parse_first_valid_llm_json,
)
from infini_local.pipelines import (
    combine_pipeline,
    image_backend_pipeline,
    visual_generation_pipeline,
)
from infini_local.pipelines.combine_pipeline import (
    apply_family_locks_to_genome,
    apply_parent_projectile_affordance,
    attach_gameplay_and_attack,
    clear_combine_failure,
    infer_projectile_visual_family,
    last_combine_failure_summary,
    record_combine_failure,
    validate_and_repair,
)
from infini_local.pipelines.engine_pressure_metrics import (
    behavior_cost_multiplier,
    sanitize_genome_engine,
)
from infini_local.pipelines.generated_parent_summary import (
    generated_parent_summary_from_data,
)
from infini_local.pipelines.image_backend_pipeline import (
    build_sdcpp_server_command,
    sdcpp_server_payload,
)
from infini_local.pipelines.item_power_knowledge import (
    apply_item_knowledge,
    canonicalize,
    infer_item_card,
)
from infini_local.pipelines.llm_authoring_pipeline import (
    authored_weapon_damage,
    build_llm_author_payload,
    engine_runtime_capability_contract_for_llm,
    llm_chat_json,
    planner_prompt_usability_report,
)
from infini_local.pipelines.parent_context_pipeline import (
    behavior_policy_for_prompt,
    effective_projectile_profile_of,
    projectile_behavior_digest_for_llm,
    projectile_profile_of,
    raw_parent_card_for_llm,
)
from infini_local.pipelines.sprite_processing_pipeline import (
    alpha_stats,
    postprocess_sprite,
    sprite_validation_fatal,
    validate_processed_sprite,
)
from infini_local.pipelines.visual_generation_pipeline import (
    asset_negative_prompt,
    build_visual_asset_plan,
    image_backend_is_zimage,
    normalize_asset_prompt,
)
from infini_local.services import (
    sdcpp_backend,
)
from infini_local.services.visual_asset_pipeline import (
    strip_conflicting_sprite_prompt_bits,
    zimage_pe_clean_text,
)
from infini_local.storage.world_recipe_runtime import (
    sanitize_recipe_for_delivery,
)
from infini_local.web.server import (
    EFFECT_CODE,
    MOVEMENT_CODE,
    ONHIT_CODE,
    SDCPP_DEFAULT_COMMAND_TEMPLATE,
    Handler,
    LLM_MAX_TOKENS,
    SDCPP_HEIGHT,
    SDCPP_TIMEOUT,
    final_normalize,
    main,
    trace_snapshot,
    trace_snapshot_html,
)

__all__ = [
    "EFFECT_CODE",
    "MOVEMENT_CODE",
    "ONHIT_CODE",
    "SDCPP_DEFAULT_COMMAND_TEMPLATE",
    "alpha_stats",
    "apply_family_locks_to_genome",
    "apply_item_knowledge",
    "apply_parent_projectile_affordance",
    "asset_negative_prompt",
    "attach_gameplay_and_attack",
    "authored_weapon_damage",
    "behavior_cost_multiplier",
    "behavior_policy_for_prompt",
    "build_llm_author_payload",
    "build_sdcpp_server_command",
    "build_visual_asset_plan",
    "canonicalize",
    "clear_combine_failure",
    "combine_pipeline",
    "effective_projectile_profile_of",
    "engine_runtime_capability_contract_for_llm",
    "generated_parent_summary_from_data",
    "image_backend_is_zimage",
    "image_backend_pipeline",
    "infer_item_card",
    "infer_projectile_visual_family",
    "last_combine_failure_summary",
    "llm_chat_json",
    "normalize_asset_prompt",
    "parse_first_valid_llm_json",
    "planner_prompt_usability_report",
    "postprocess_sprite",
    "projectile_behavior_digest_for_llm",
    "projectile_profile_of",
    "raw_parent_card_for_llm",
    "record_combine_failure",
    "sanitize_genome_engine",
    "sanitize_recipe_for_delivery",
    "sdcpp_backend",
    "sdcpp_server_payload",
    "sprite_validation_fatal",
    "strip_conflicting_sprite_prompt_bits",
    "validate_and_repair",
    "validate_processed_sprite",
    "visual_generation_pipeline",
    "zimage_pe_clean_text",
    "Handler",
    "LLM_MAX_TOKENS",
    "SDCPP_HEIGHT",
    "SDCPP_TIMEOUT",
    "final_normalize",
    "main",
    "trace_snapshot",
    "trace_snapshot_html",
]
