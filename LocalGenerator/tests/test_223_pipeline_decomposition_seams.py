from __future__ import annotations

from infini_local.pipelines import (
    category_policy as _cat,
    combine_orchestrator as _comb,
    engine_pressure_metrics as _epm,
    equipment_stats as _equip,
    final_normalize as _fnorm,
    generation_debug as _gdbg,
    generated_parent_summary as _gps,
    item_power_knowledge as _ipow,
    item_rarity_baseline as _irarity,
    parent_context_cards as _pcards,
    parent_context_pipeline as _pctx,
    presentation_sound as _psound,
    projectile_affordance as _proj,
    repair_orchestrator as _rep,
    result_identity_policy as _rid,
    result_knowledge_card as _rkc,
    sprite_contracts as _scontracts,
    sprite_geometry as _sgeo,
    sprite_keyer as _skey,
    sprite_postprocess as _spost,
    sprite_processing_pipeline as _sprite,
    stat_profile as _stat,
)


def test_stat_profile_seam_exposes_expected_callables():
    assert callable(_stat.stat_profile_for)
    assert callable(_stat.stage_profile_for)
    assert callable(_stat.parent_source_damage)
    assert "stat_profile_for" in _stat.__all__
    assert "stage_profile_for" in _stat.__all__


def test_final_normalize_seam_exposes_expected_callables():
    assert callable(_fnorm.final_normalize)
    assert callable(_fnorm.normalize_generated_item_json)
    assert "final_normalize" in _fnorm.__all__


def test_generation_debug_seam_exposes_expected_callables():
    for name in ("record_combine_failure", "clear_combine_failure", "last_combine_failure_summary", "compact_json_debug"):
        assert callable(getattr(_gdbg, name))
        assert name in _gdbg.__all__


def test_repair_orchestrator_seam_exposes_expected_callables():
    for name in ("validate_and_repair", "repair_name_if_needed", "canonical_for_result", "reduce_targeted_repair_patch"):
        assert callable(getattr(_rep, name))
        assert name in _rep.__all__


def test_result_identity_policy_seam_exposes_expected_callables():
    for name in ("creative_result_name", "category_policy", "canonical_for_result", "repair_name_if_needed"):
        assert callable(getattr(_rid, name))
        assert name in _rid.__all__


def test_equipment_stats_seam_exposes_expected_callables():
    for name in ("accessory_stats_for", "armor_stats_for", "apply_accessory_soft_budget", "apply_armor_soft_budget"):
        assert callable(getattr(_equip, name))
        assert name in _equip.__all__


def test_projectile_affordance_seam_exposes_expected_callables():
    for name in ("infer_projectile_visual_family", "choose_parent_projectile_size_reference", "apply_parent_projectile_affordance"):
        assert callable(getattr(_proj, name))
        assert name in _proj.__all__


def test_presentation_sound_seam_exposes_expected_callables():
    for name in ("presentation_from_genome", "sound_profile_from_genome", "attach_presentation_and_sound"):
        assert callable(getattr(_psound, name))
        assert name in _psound.__all__


def test_result_knowledge_card_seam_exposes_expected_callables():
    for name in ("build_result_item_card", "attach_result_knowledge_card"):
        assert callable(getattr(_rkc, name))
        assert name in _rkc.__all__


def test_item_power_knowledge_seam_exposes_expected_callables():
    for name in ("tags_of", "mechanic_signal_power", "infer_item_card", "build_item_knowledge", "apply_item_knowledge"):
        assert callable(getattr(_ipow, name))
        assert name in _ipow.__all__
    assert "TIER_DEFAULT_POWER" in _ipow.__all__
    for name in ("rarity_tier_estimate", "rarity_baseline_signal", "modded_rarity_entry"):
        assert callable(getattr(_irarity, name))
        assert getattr(_ipow, name) is getattr(_irarity, name)
        assert name in _ipow.__all__


def test_generated_parent_summary_seam_exposes_expected_callables():
    for name in ("generated_parent_summary_from_data", "attach_generated_parent_summary"):
        assert callable(getattr(_gps, name))
        assert name in _gps.__all__


def test_parent_context_card_seam_exposes_expected_callables():
    assert callable(_pcards.raw_parent_card_for_llm)
    assert callable(_pctx.raw_parent_card_for_llm)
    assert _pctx.raw_parent_card_for_llm({"name": "A"})["name"] == _pcards.raw_parent_card_for_llm({"name": "A"})["name"]


def test_engine_pressure_metrics_seam_exposes_expected_callables():
    for name in ("behavior_cost_multiplier", "estimate_engine_metrics", "sanitize_genome_engine", "clamp_float", "dict_get_ci"):
        assert callable(getattr(_epm, name))
        assert name in _epm.__all__


def test_combine_orchestrator_seam_exposes_expected_callables():
    for name in ("combine", "combine_cache_lookup", "run_combine_orchestration"):
        assert callable(getattr(_comb, name))
        assert name in _comb.__all__


def test_vfx_composition_seams_expose_expected_callables():
    from infini_local.core import vfx_composition as facade
    from infini_local.core import vfx_composition_parent as parent
    from infini_local.core import vfx_composition_primitives as primitives
    from infini_local.core import vfx_runtime_slots as runtime_slots

    for name in ("_vfx_infer_channel", "_vfx_arbitrate_slots", "_vfx_resolve_particle_system_id"):
        assert callable(getattr(primitives, name))
        assert getattr(facade, name) is getattr(primitives, name)
        assert name in facade.__all__
    for name in ("_vfx_parent_effect_profile", "_vfx_parent_inherited_raw_slots"):
        assert callable(getattr(parent, name))
        assert getattr(facade, name) is getattr(parent, name)
        assert name in facade.__all__
    for name in ("_vfx_compile_slot", "_vfx_runtime_plan_direct_manifest", "_vfx_authored_cue_raw_slots"):
        assert callable(getattr(runtime_slots, name))
        assert getattr(facade, name) is getattr(runtime_slots, name)
        assert name in facade.__all__


def test_sprite_processing_seams_expose_expected_callables():
    for name in ("alpha_bbox_threshold", "sprite_bbox_stats"):
        assert callable(getattr(_sgeo, name))
        assert getattr(_sprite, name) is getattr(_sgeo, name)
        assert name in _sprite.__all__
    for name in ("remove_background_sprite_keyer", "apply_background_removal", "magenta_key_pixel_ratio"):
        assert callable(getattr(_skey, name))
        assert getattr(_sprite, name) is getattr(_skey, name)
        assert name in _sprite.__all__
    for name in ("postprocess_sprite", "validate_processed_sprite", "build_retry_prompt_from_validation"):
        assert callable(getattr(_spost, name))
        assert getattr(_sprite, name) is getattr(_spost, name)
        assert name in _sprite.__all__
    for name in ("sprite_contract_for", "chroma_rgb"):
        assert callable(getattr(_scontracts, name))
        assert name in _scontracts.__all__


def test_category_policy_core_constants_and_pipeline_wrapper():
    from infini_local.core.category_policy import ALLOWED_CATEGORIES as core_allowed

    assert "weapon" in core_allowed
    assert _cat.ALLOWED_CATEGORIES is core_allowed
    assert _cat.runtime_kind_is_non_weapon("accessory") is True
    assert _cat.category_intent_summary({"runtimePlan": {"engineCalls": [{"fn": "shoot_projectile"}]}})["hasRuntimePlan"] is True


def test_seam_modules_forward_real_implementations_not_stubs():
    from infini_local.pipelines.combine_pipeline import stat_profile_for as cp_stats
    from infini_local.pipelines.pipeline_support import behavior_cost_multiplier as ps_behavior_cost
    from infini_local.pipelines.pipeline_support import final_normalize as ps_fnorm
    from infini_local.pipelines.pipeline_support import generated_parent_summary_from_data as ps_gps
    from infini_local.pipelines.pipeline_support import tags_of as ps_tags_of
    from infini_local.web import api as web_server

    assert _stat.stat_profile_for is cp_stats
    assert _fnorm.final_normalize is ps_fnorm
    assert _ipow.tags_of is ps_tags_of
    assert _gps.generated_parent_summary_from_data is ps_gps
    assert _gps.generated_parent_summary_from_data is web_server.generated_parent_summary_from_data
    assert _epm.behavior_cost_multiplier is ps_behavior_cost
    assert _epm.behavior_cost_multiplier is web_server.behavior_cost_multiplier
