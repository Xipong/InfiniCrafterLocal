from __future__ import annotations

from typing import Any

# Version names are intentionally semantic, not only numeric.  Generated recipes can be
# inspected later without guessing which prompt/runtime/visual contract authored them.
PLANNER_PROMPT_PROFILE_VERSION = "planner_prompt_compressed_human_prose_v0.4.193"
VISUAL_ROLE_CONTRACT_VERSION = "careful_visual_role_prompt_hygiene_v0.4.171"
RUNTIME_AFFORDANCE_SCHEMA_VERSION = "infini.runtime-affordance.v2"
FAILURE_UX_CONTRACT_VERSION = "structured_failure_player_message_v0.4.174"
DEBUG_DUMP_CONTRACT_VERSION = "compact_recipe_debug_dump_v0.4.174"
RUNTIME_STATE_CLEANUP_CONTRACT_VERSION = "runtime_state_cleanup_v0.4.175"
LOCAL_CACHE_AND_REPAIR_CONTRACT_VERSION = "local_cache_runtime_repair_contract_cleanup_v0.4.176"
CSHARP_AUTHORING_PRESERVATION_CONTRACT_VERSION = "csharp_authoring_extension_preservation_v0.4.177"
PARENT_PROJECTILE_SIZE_PRESERVATION_CONTRACT_VERSION = "llm_opt_in_parent_projectile_size_policy_v0.4.179"
RUNTIME_REPAIR_OBSERVABILITY_CONTRACT_VERSION = "runtime_repair_path_preservation_v0.4.180"
RELEASE_HYGIENE_GUARD_CONTRACT_VERSION = "release_hygiene_zone_identifier_guard_v0.4.181"
CSHARP_CONTRACT_SYNC_GUARD_VERSION = "csharp_future_field_contract_guard_v0.4.181"
RELEASE_VERSION_SYNC_GUARD_VERSION = "release_version_sync_guard_v0.4.182"
RELEASE_HYGIENE_TEST_CONTRACT_VERSION = "release_hygiene_tool_regression_tests_v0.4.182"
PYTHON_EXCEPTION_HYGIENE_GUARD_VERSION = "python_exception_hygiene_baseline_guard_v0.4.183"
RUNTIME_API_SYNC_GUARD_VERSION = "runtime_api_python_csharp_sync_guard_v0.4.183"
FISHING_BAIT_FUTURE_DISABLED_PARENT_CONTEXT_VERSION = "fishing_bait_future_disabled_parent_context_v0.4.184"
PROJECTILE_CHILD_RUNTIME_GUARD_VERSION = "projectile_child_runtime_static_guard_v0.4.184"
PROJECTILE_CHAIN_CHILD_GUARD_VERSION = "projectile_chain_child_count_guard_v0.4.185"
VFX_AUDIO_PRESENTATION_GUARD_VERSION = "vfx_audio_presentation_guard_v0.4.185"
SOUND_LIBRARY_CONTRACT_VERSION = "expanded_vanilla_soundid_selector_v0.4.192"
LUMINANCE_SOUND_BRIDGE_CONTRACT_VERSION = "external_luminance_looped_sound_bridge_v0.4.187"
FUTURE_SOUND_CATALOG_SEAM_VERSION = "embedding_sound_catalog_future_seam_v0.4.190"
GENERATED_ARMOR_CONTRACT_VERSION = "generated_armor_proxy_slots_v0.4.192"
ARMOR_PROPERTY_ROUNDTRIP_CONTRACT_VERSION = "armor_extended_property_slot_budget_roundtrip_v0.4.192"
PROMPT_COMPRESSION_CONTRACT_VERSION = "planner_prompt_compression_preserve_prose_v0.4.193"
MULTIPLAYER_PRESENTATION_SYNC_CONTRACT_VERSION = "held_pose_accessory_compile_hotfix_v0.4.199"
VANILLA_PRESENTATION_POLISH_CONTRACT_VERSION = "bounded_vanilla_presentation_polish_v0.4.199"
HELD_ITEM_POSE_SYNC_CONTRACT_VERSION = "held_item_pose_accessory_compile_hotfix_v0.4.199"
BUILD_QOL_CONTRACT_VERSION = "tml_build_log_qol_and_compile_surface_cleanup_v0.4.201"
GAMEPLAY_QOL_CONTRACT_VERSION = "generated_use_feedback_tooltip_qol_v0.4.201"
OVERHAUL_QOL_CONTRACT_VERSION = "infini_station_overhaul_qol_v0.4.202"
MAINTENANCE_QOL_CONTRACT_VERSION = "maintainability_gameplay_qol_cleanup_v0.4.203"
RUNTIME_GAMEPLAY_QOL_CONTRACT_VERSION = "impact_mobility_cooldown_and_sprite_lru_qol_v0.4.204"
MAINTENANCE_HARDENING_CONTRACT_VERSION = "repair_json_sync_and_low_noise_fallback_logs_v0.4.205"
VANILLA_RUNTIME_SPRITE_CACHE_CONTRACT_VERSION = "runtime_sprite_max_side_192_hotfix_v0.4.207"
REBUILD_GAMEPLAY_CACHE_DIAGNOSTICS_CONTRACT_VERSION = "generated_melee_onhit_and_cache_diagnostics_v0.4.209"
GAMEPLAY_RUNTIME_REBUILD_CONTRACT_VERSION = "runtime_coverage_station_ux_balance_envelope_v0.4.212"
BALANCE_SINGLE_AUTHORITY_CONTRACT_VERSION = "code_owned_balance_envelope_no_active_guide_helper_v0.4.216"
REPO_CLEANUP_BROAD_BALANCE_CONTRACT_VERSION = "repo_docs_cleanup_and_broad_soft_balance_uplift_v0.4.216"
BALANCE_ARCHITECTURE_AUDIT_CONTRACT_VERSION = "prompt_free_parent_soft_caps_code_owned_balance_audit_v0.4.216"
REPAIR_BOUNDARY_CONTRACT_VERSION = "code_structural_repair_then_targeted_runtime_retry_v0.4.217"
MP_SERVER_AUTHORITY_ENV_MIGRATION_CI_CONTRACT_VERSION = "server_side_slot_spend_env_migration_ci_hardening_v0.4.218"
ARCHITECTURE_COHERENCE_CONTRACT_VERSION = "single_balance_report_clamp_taxonomy_powerband_v0.4.219"
REPAIR_PATCH_CONTRACT_VERSION = "targeted_repair_reduced_to_runtime_patch_v0.4.220"
ARCHITECTURE_HOMOGENEITY_CONTRACT_VERSION = "central_balance_policy_and_csharp_runtime_constants_v0.4.226"
ENV_ACCESS_CONTRACT_VERSION = "centralized_env_access_no_import_star_v0.4.226"
RUNTIME_PROVENANCE_CONTRACT_VERSION = "runtime_authored_applied_provenance_debug_v0.4.226"
EQUIPMENT_BUDGET_CONTRACT_VERSION = "armor_accessory_total_soft_budget_v0.4.226"
REPLAY_HARNESS_CONTRACT_VERSION = "generation_case_replay_audit_v0.4.226"
ALT_FORK_CHERRYPICK_CONTRACT_VERSION = "best_of_alt_config_signals_trace_replay_v0.4.226"
RUNTIME_ARCHETYPE_SCHEMA_VERSION = "infini.runtime-archetype.v1"
RUNTIME_CONTRACT_SCHEMA_VERSION = "infini.runtime-contract.v1"
RUNTIME_PROMISE_TRUTH_CONTRACT_VERSION = "runtime_promise_truth_validator_v0.4.237"
RECIPE_HEALTH_SCHEMA_VERSION = "infini.recipe-health.v1"
CONTRACT_STAMP_SCHEMA_VERSION = "infini.contract-stamp.v1"

# Notes distilled from tModLoader docs/guides for grey zones that affect generated
# items. These are descriptive diagnostics only; they do not route gameplay.
TMODLOADER_GREY_ZONE_NOTES: dict[str, str] = {
    "holdoutOffset": "ModItem.HoldoutOffset is relevant for useStyle 5 non-staff held items; other use styles need different draw/hold paths.",
    "heldAnimation": "HoldItemFrame/HoldStyle can affect held animation/location, while projectile movement/rotation lives on the projectile path.",
    "projectileRotation": "Projectile sprites generally need an explicit rotation policy such as face velocity, fixed, or spin; the PNG alone is not a throw animation.",
    "projectileNetState": "Projectile.ai fields sync automatically, while custom AI state needs SendExtraAI/ReceiveExtraAI or careful netUpdate use.",
}


def build_contract_versions(
    *,
    app_version: str,
    recipe_identity_version: str,
    runtime_api_version: str,
    visual_pipeline_profile: str,
    planner_prompt_profile: str = PLANNER_PROMPT_PROFILE_VERSION,
    visual_role_contract: str = VISUAL_ROLE_CONTRACT_VERSION,
) -> dict[str, Any]:
    """Return the compact contract stamp written into every new recipe.

    This is observability, not compatibility gating: it helps distinguish an old
    recipe artifact from a current runtime problem while keeping test worlds cheap.
    """
    return {
        "schema": CONTRACT_STAMP_SCHEMA_VERSION,
        "appVersion": str(app_version),
        "recipeIdentityVersion": str(recipe_identity_version),
        "runtimeApiVersion": str(runtime_api_version),
        "visualPipelineProfile": str(visual_pipeline_profile),
        "plannerPromptProfile": str(planner_prompt_profile),
        "visualRoleContract": str(visual_role_contract),
        "runtimeAffordanceSchema": RUNTIME_AFFORDANCE_SCHEMA_VERSION,
        "failureUxContract": FAILURE_UX_CONTRACT_VERSION,
        "debugDumpContract": DEBUG_DUMP_CONTRACT_VERSION,
        "runtimeStateCleanupContract": RUNTIME_STATE_CLEANUP_CONTRACT_VERSION,
        "localCacheAndRepairContract": LOCAL_CACHE_AND_REPAIR_CONTRACT_VERSION,
        "csharpAuthoringPreservationContract": CSHARP_AUTHORING_PRESERVATION_CONTRACT_VERSION,
        "parentProjectileSizePreservationContract": PARENT_PROJECTILE_SIZE_PRESERVATION_CONTRACT_VERSION,
        "runtimeRepairObservabilityContract": RUNTIME_REPAIR_OBSERVABILITY_CONTRACT_VERSION,
        "releaseHygieneGuardContract": RELEASE_HYGIENE_GUARD_CONTRACT_VERSION,
        "csharpContractSyncGuard": CSHARP_CONTRACT_SYNC_GUARD_VERSION,
        "releaseVersionSyncGuard": RELEASE_VERSION_SYNC_GUARD_VERSION,
        "releaseHygieneToolTestContract": RELEASE_HYGIENE_TEST_CONTRACT_VERSION,
        "pythonExceptionHygieneGuard": PYTHON_EXCEPTION_HYGIENE_GUARD_VERSION,
        "runtimeApiSyncGuard": RUNTIME_API_SYNC_GUARD_VERSION,
        "fishingBaitFutureDisabledParentContext": FISHING_BAIT_FUTURE_DISABLED_PARENT_CONTEXT_VERSION,
        "projectileChildRuntimeGuard": PROJECTILE_CHILD_RUNTIME_GUARD_VERSION,
        "projectileChainChildGuard": PROJECTILE_CHAIN_CHILD_GUARD_VERSION,
        "vfxAudioPresentationGuard": VFX_AUDIO_PRESENTATION_GUARD_VERSION,
        "soundLibraryContract": SOUND_LIBRARY_CONTRACT_VERSION,
        "luminanceSoundBridgeContract": LUMINANCE_SOUND_BRIDGE_CONTRACT_VERSION,
        "futureSoundCatalogSeam": FUTURE_SOUND_CATALOG_SEAM_VERSION,
        "generatedArmorContract": GENERATED_ARMOR_CONTRACT_VERSION,
        "armorPropertyRoundtripContract": ARMOR_PROPERTY_ROUNDTRIP_CONTRACT_VERSION,
        "promptCompressionContract": PROMPT_COMPRESSION_CONTRACT_VERSION,
        "multiplayerPresentationSyncContract": MULTIPLAYER_PRESENTATION_SYNC_CONTRACT_VERSION,
        "vanillaPresentationPolishContract": VANILLA_PRESENTATION_POLISH_CONTRACT_VERSION,
        "heldItemPoseSyncContract": HELD_ITEM_POSE_SYNC_CONTRACT_VERSION,
        "buildQolContract": BUILD_QOL_CONTRACT_VERSION,
        "gameplayQolContract": GAMEPLAY_QOL_CONTRACT_VERSION,
        "overhaulQolContract": OVERHAUL_QOL_CONTRACT_VERSION,
        "maintenanceQolContract": MAINTENANCE_QOL_CONTRACT_VERSION,
        "runtimeGameplayQolContract": RUNTIME_GAMEPLAY_QOL_CONTRACT_VERSION,
        "maintenanceHardeningContract": MAINTENANCE_HARDENING_CONTRACT_VERSION,
        "vanillaRuntimeSpriteCacheContract": VANILLA_RUNTIME_SPRITE_CACHE_CONTRACT_VERSION,
        "rebuildGameplayCacheDiagnosticsContract": REBUILD_GAMEPLAY_CACHE_DIAGNOSTICS_CONTRACT_VERSION,
        "gameplayRuntimeRebuildContract": GAMEPLAY_RUNTIME_REBUILD_CONTRACT_VERSION,
        "balanceSingleAuthorityContract": BALANCE_SINGLE_AUTHORITY_CONTRACT_VERSION,
        "repoCleanupBroadBalanceContract": REPO_CLEANUP_BROAD_BALANCE_CONTRACT_VERSION,
        "balanceArchitectureAuditContract": BALANCE_ARCHITECTURE_AUDIT_CONTRACT_VERSION,
        "repairBoundaryContract": REPAIR_BOUNDARY_CONTRACT_VERSION,
        "mpServerAuthorityEnvMigrationCiContract": MP_SERVER_AUTHORITY_ENV_MIGRATION_CI_CONTRACT_VERSION,
        "architectureCoherenceContract": ARCHITECTURE_COHERENCE_CONTRACT_VERSION,
        "repairPatchContract": REPAIR_PATCH_CONTRACT_VERSION,
        "architectureHomogeneityContract": ARCHITECTURE_HOMOGENEITY_CONTRACT_VERSION,
        "envAccessContract": ENV_ACCESS_CONTRACT_VERSION,
        "runtimeProvenanceContract": RUNTIME_PROVENANCE_CONTRACT_VERSION,
        "equipmentBudgetContract": EQUIPMENT_BUDGET_CONTRACT_VERSION,
        "replayHarnessContract": REPLAY_HARNESS_CONTRACT_VERSION,
        "altForkCherrypickContract": ALT_FORK_CHERRYPICK_CONTRACT_VERSION,
        "runtimeArchetypeSchema": RUNTIME_ARCHETYPE_SCHEMA_VERSION,
        "runtimeContractSchema": RUNTIME_CONTRACT_SCHEMA_VERSION,
        "runtimePromiseTruthContract": RUNTIME_PROMISE_TRUTH_CONTRACT_VERSION,
        "recipeHealthSchema": RECIPE_HEALTH_SCHEMA_VERSION,
    }
