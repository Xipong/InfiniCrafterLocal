from __future__ import annotations

from infini_local.pipelines import (
    category_policy as _cat,
    combine_orchestrator as _comb,
    final_normalize as _fnorm,
    generation_debug as _gdbg,
    repair_orchestrator as _rep,
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


def test_combine_orchestrator_seam_exposes_expected_callables():
    for name in ("combine", "combine_cache_lookup", "run_combine_orchestration"):
        assert callable(getattr(_comb, name))
        assert name in _comb.__all__


def test_category_policy_core_constants_and_pipeline_wrapper():
    from infini_local.core.category_policy import ALLOWED_CATEGORIES as core_allowed

    assert "weapon" in core_allowed
    assert _cat.ALLOWED_CATEGORIES is core_allowed
    assert _cat.runtime_kind_is_non_weapon("accessory") is True
    assert _cat.category_intent_summary({"runtimePlan": {"engineCalls": [{"fn": "shoot_projectile"}]}})["hasRuntimePlan"] is True


def test_seam_modules_forward_real_implementations_not_stubs():
    from infini_local.pipelines.combine_pipeline import stat_profile_for as cp_stats
    from infini_local.pipelines.pipeline_support import final_normalize as ps_fnorm

    assert _stat.stat_profile_for is cp_stats
    assert _fnorm.final_normalize is ps_fnorm
