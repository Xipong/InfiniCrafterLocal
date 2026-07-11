from __future__ import annotations

import ast
from pathlib import Path

from infini_local.pipelines import (
    category_policy as _cat,
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
    result_identity_policy as _rid,
    result_knowledge_card as _rkc,
    sprite_contracts as _scontracts,
    sprite_geometry as _sgeo,
    sprite_keyer as _skey,
    sprite_postprocess as _spost,
    stat_profile as _stat,
)


def test_stat_profile_seam_exposes_expected_callables():
    from infini_local.pipelines import combine_balance

    assert callable(_stat.parent_source_damage)
    assert callable(_stat.stat_profile_summary)
    assert not hasattr(_stat, "stat_profile_for")
    assert not hasattr(_stat, "stage_profile_for")
    assert callable(combine_balance.stat_profile_for)
    assert not hasattr(combine_balance, "stage_profile_for")


def test_final_normalize_seam_exposes_expected_callables():
    assert callable(_fnorm.final_normalize)
    assert callable(_fnorm.normalize_generated_item_json)
    assert "final_normalize" in _fnorm.__all__
    assert _fnorm.final_normalize.__module__ == _fnorm.__name__


def test_generation_debug_seam_exposes_expected_callables():
    for name in ("record_combine_failure", "clear_combine_failure", "last_combine_failure_summary", "compact_json_debug"):
        assert callable(getattr(_gdbg, name))
        assert name in _gdbg.__all__
    assert _gdbg.record_combine_failure.__module__ == _gdbg.__name__
    assert _gdbg.clear_combine_failure.__module__ == _gdbg.__name__
    assert _gdbg.last_combine_failure_summary.__module__ == _gdbg.__name__


def test_dead_repair_orchestrator_facade_is_retired():
    pipelines_dir = Path(__file__).resolve().parents[1] / "infini_local" / "pipelines"
    assert not (pipelines_dir / "repair_orchestrator.py").exists()

def test_non_package_modules_import_only_symbols_they_execute():
    package_dir = Path(__file__).resolve().parents[1] / "infini_local"
    for module_path in package_dir.rglob("*.py"):
        if module_path.name == "__init__.py":
            continue
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        loaded_names = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        unused: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue
                unused.extend(
                    alias.asname or alias.name
                    for alias in node.names
                    if (alias.asname or alias.name) not in loaded_names
                )
            elif isinstance(node, ast.Import):
                unused.extend(
                    alias.asname or alias.name.split(".", 1)[0]
                    for alias in node.names
                    if (alias.asname or alias.name.split(".", 1)[0]) not in loaded_names
                )
        assert unused == [], f"{module_path.relative_to(package_dir)}: {unused}"


def test_infini_local_import_graph_is_acyclic():
    package_dir = Path(__file__).resolve().parents[1] / "infini_local"
    modules = {
        ".".join(path.relative_to(package_dir.parent).with_suffix("").parts): path
        for path in package_dir.rglob("*.py")
    }
    edges: dict[str, set[str]] = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in modules:
                edges[module].add(node.module)
            elif isinstance(node, ast.Import):
                edges[module].update(alias.name for alias in node.names if alias.name in modules)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str, path: tuple[str, ...]) -> None:
        if module in visiting:
            cycle_start = path.index(module)
            raise AssertionError(" -> ".join((*path[cycle_start:], module)))
        if module in visited:
            return
        visiting.add(module)
        for dependency in edges[module]:
            visit(dependency, (*path, module))
        visiting.remove(module)
        visited.add(module)

    for module in modules:
        visit(module, ())


def test_module_exports_are_static_not_globals_driven():
    package_dir = Path(__file__).resolve().parents[1] / "infini_local"
    offenders: list[str] = []
    for path in package_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                continue
            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "globals"
                for child in ast.walk(node.value)
            ):
                offenders.append(str(path.relative_to(package_dir)))
    assert offenders == []


def test_declared_module_exports_exist_at_runtime():
    import importlib
    import pkgutil

    import infini_local

    missing: dict[str, list[str]] = {}
    for info in pkgutil.walk_packages(infini_local.__path__, infini_local.__name__ + "."):
        module = importlib.import_module(info.name)
        absent = [name for name in getattr(module, "__all__", ()) if not hasattr(module, name)]
        if absent:
            missing[info.name] = absent
    assert missing == {}


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
    for name in ("presentation_from_genome", "attach_presentation_and_sound"):
        assert callable(getattr(_psound, name))
        assert name in _psound.__all__
    assert not hasattr(_psound, "sound_profile_from_genome")


def test_result_knowledge_card_seam_exposes_expected_callables():
    for name in ("build_result_item_card", "attach_result_knowledge_card"):
        assert callable(getattr(_rkc, name))
        assert name in _rkc.__all__


def test_item_power_knowledge_seam_exposes_expected_callables():
    for name in ("tags_of", "mechanic_signal_power", "infer_item_card", "build_item_knowledge", "apply_item_knowledge"):
        assert callable(getattr(_ipow, name))
        assert name in _ipow.__all__
    for name in ("rarity_tier_estimate", "rarity_baseline_signal", "modded_rarity_entry"):
        assert callable(getattr(_irarity, name))
        assert name in _irarity.__all__
        assert name not in _ipow.__all__
    assert not hasattr(_ipow, "rarity_tier_estimate")
    assert not hasattr(_ipow, "modded_rarity_entry")
    assert "TIER_DEFAULT_POWER" in _irarity.__all__
    assert "TIER_DEFAULT_POWER" not in _ipow.__all__


def test_generated_parent_summary_seam_exposes_expected_callables():
    for name in ("generated_parent_summary_from_data", "attach_generated_parent_summary"):
        assert callable(getattr(_gps, name))
        assert name in _gps.__all__


def test_parent_context_card_seam_exposes_expected_callables():
    assert callable(_pcards.raw_parent_card_for_llm)
    assert not hasattr(_pctx, "raw_parent_card_for_llm")


def test_engine_pressure_metrics_seam_exposes_expected_callables():
    for name in ("behavior_cost_multiplier", "estimate_engine_metrics", "sanitize_genome_engine", "clamp_float", "dict_get_ci"):
        assert callable(getattr(_epm, name))
        assert name in _epm.__all__


def test_dead_combine_orchestrator_facade_is_retired():
    pipelines_dir = Path(__file__).resolve().parents[1] / "infini_local" / "pipelines"
    assert not (pipelines_dir / "combine_orchestrator.py").exists()


def test_vfx_composition_seams_expose_expected_callables():
    from infini_local.core import vfx_composition_parent as parent
    from infini_local.core import vfx_composition_primitives as primitives
    from infini_local.core import vfx_runtime_slots as runtime_slots

    for name in ("_vfx_infer_channel", "_vfx_arbitrate_slots", "_vfx_resolve_particle_system_id"):
        assert callable(getattr(primitives, name))
    for name in ("_vfx_parent_effect_profile", "_vfx_parent_inherited_raw_slots"):
        assert callable(getattr(parent, name))
    for name in ("_vfx_compile_slot", "_vfx_runtime_plan_direct_manifest", "_vfx_authored_cue_raw_slots"):
        assert callable(getattr(runtime_slots, name))
    core_dir = Path(__file__).resolve().parents[1] / "infini_local" / "core"
    assert not (core_dir / "vfx_composition.py").exists()


def test_sprite_processing_seams_expose_expected_callables():
    for name in ("alpha_bbox_threshold", "sprite_bbox_stats"):
        assert callable(getattr(_sgeo, name))
    for name in ("remove_background_sprite_keyer", "apply_background_removal", "magenta_key_pixel_ratio"):
        assert callable(getattr(_skey, name))
    for name in ("postprocess_sprite", "validate_processed_sprite", "build_retry_prompt_from_validation"):
        assert callable(getattr(_spost, name))
    for name in ("sprite_contract_for", "chroma_rgb"):
        assert callable(getattr(_scontracts, name))
        assert name in _scontracts.__all__
    pipelines_dir = Path(__file__).resolve().parents[1] / "infini_local" / "pipelines"
    assert not (pipelines_dir / "sprite_processing_pipeline.py").exists()


def test_category_policy_core_constants_and_pipeline_wrapper():
    from infini_local.core.category_policy import ALLOWED_CATEGORIES as core_allowed

    assert "weapon" in core_allowed
    assert not hasattr(_cat, "ALLOWED_CATEGORIES")
    assert _cat.runtime_kind_is_non_weapon("accessory") is True
    assert _cat.category_intent_summary({"runtimePlan": {"engineCalls": [{"fn": "shoot_projectile"}]}})["hasRuntimePlan"] is True


def test_seam_modules_forward_real_implementations_not_stubs():
    from infini_local.pipelines.engine_pressure_metrics import behavior_cost_multiplier as ps_behavior_cost
    from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data as ps_gps
    from infini_local.pipelines.item_power_knowledge import tags_of as ps_tags_of
    from infini_local.pipelines.engine_pressure_metrics import behavior_cost_multiplier
    from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data

    assert _ipow.tags_of is ps_tags_of
    assert _gps.generated_parent_summary_from_data is ps_gps
    assert _gps.generated_parent_summary_from_data is generated_parent_summary_from_data
    assert _epm.behavior_cost_multiplier is ps_behavior_cost
    assert _epm.behavior_cost_multiplier is behavior_cost_multiplier
