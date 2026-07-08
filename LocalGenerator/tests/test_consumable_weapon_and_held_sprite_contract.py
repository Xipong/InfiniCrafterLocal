from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines.llm_authoring_pipeline import llm_runtime_result_kind_policy

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[1]
CS_ROOT = ROOT.parent / "ModSources" / "InfiniCrafterLocal"


def _check_consumable_weapon_runtime_kind_keeps_weapon_executor_alive() -> None:
    data = {
        "category": "potion",
        "runtimePlan": {
            "resultKind": "consumable_weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "consumable_weapon", "damage": 0, "maxStack": 30}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "throw", "delivery": "throw", "movement": "gravity_arc", "speed": 7, "rangeTiles": 20, "lifetimeTicks": 90}},
            ],
        },
    }
    kind, policy = llm_runtime_result_kind_policy(data, "potion", {"potion", "bomb"}, {}, {}, "test")
    assert kind == "weapon"
    assert policy["runtimeResultKind"] == "consumable_weapon"


def _check_csharp_attack_setup_is_not_gated_by_positive_damage() -> None:
    model = read_text_with_partial_bundles(CS_ROOT / "Common" / "Models" / "GeneratedItemData.cs")
    assert "Gameplay.Damage > 0 && Attack.Enabled" not in model
    assert "if (!isAccessory && !isArmor && Attack.Enabled && !actualAmmo)" in model


def _check_csharp_held_renderer_draws_non_weapon_generated_items() -> None:
    layer = (CS_ROOT / "Common" / "Players" / "GeneratedHeldItemDrawLayer.cs").read_text(encoding="utf-8")
    assert "gi.Data.Attack is not null && gi.Data.Attack.Enabled" not in layer
    assert "Tools/potions" in layer
    assert "held.noUseGraphic || held.useStyle > ItemUseStyleID.None" in layer
    model = read_text_with_partial_bundles(CS_ROOT / "Common" / "Models" / "GeneratedItemData.cs")
    assert "GeneratedHeldItemDrawLayer render the actual Z-Image sprite for tools" in model


def _check_csharp_alt_use_tooltip_is_visible() -> None:
    item = (CS_ROOT / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    assert "InfiniAltUse" in item
    assert "Right Click / ПКМ" in item
    assert "HasExecutableAltUse" in item


def _check_attack_enabled_is_documented_as_generated_executor_not_can_damage() -> None:
    item = (CS_ROOT / "Content" / "Items" / "GeneratedItem.cs").read_text(encoding="utf-8")
    model = read_text_with_partial_bundles(CS_ROOT / "Common" / "Models" / "GeneratedItemData.cs")
    assert "Generated executor:" in item
    assert "Damage path: vanilla item/tool hitbox only" in item
    assert "HasVanillaItemHitboxDamage" in item
    assert "Attack.Enabled means \"generated runtime executor exists\"" in item
    assert "True only when this item has an authored generated runtime executor" in model


def _check_visual_manifest_distinguishes_runtime_executor_from_vanilla_hitbox() -> None:
    visual = (ROOT / "infini_local" / "pipelines" / "visual_asset_manifest.py").read_text(encoding="utf-8")
    visual_facade = (ROOT / "infini_local" / "pipelines" / "visual_generation_pipeline.py").read_text(encoding="utf-8")
    support = (ROOT / "infini_local" / "pipelines" / "pipeline_support.py").read_text(encoding="utf-8")
    generated_summary = (ROOT / "infini_local" / "pipelines" / "generated_parent_summary.py").read_text(encoding="utf-8")
    assert "from infini_local.pipelines.visual_asset_manifest import" in visual_facade
    assert "runtimeExecutorEnabled" in visual
    assert "customAttackEnabled" in visual
    assert "vanillaItemHitboxDamage" in visual
    assert "damagePath" in visual
    assert "generated_parent_summary" in support
    assert "vanilla_item_hitbox" in generated_summary


def _check_runtime_projectiles_use_single_hit_defaults_and_ignore_spawn_target_for_children() -> None:
    projectile = read_text_with_partial_bundles(CS_ROOT / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    combine = (ROOT / "infini_local" / "pipelines" / "combine_gameplay.py").read_text(encoding="utf-8")
    assert "_spec.Pierce < 0 ? -1 : Math.Max(1, _spec.Pierce)" in projectile
    assert "_spec.Pierce <= 0 ? -1" not in projectile
    assert "localNPCHitCooldown = _spec.ImmunityCooldown <= 0 ? 12" in projectile
    assert "_spawnIgnoreNpc" in projectile
    assert "CanHitNPC" in projectile
    assert "SpawnChild(origin, velocity, dmg, childSpec, Projectile.localAI[1] + 1f, target.whoAmI)" in projectile
    assert "int(genome[\"pierce\"]) + 1" not in combine
    assert '"pierce": -1 if int(genome["pierce"]) == -1 else max(1, int(genome["pierce"]))' in combine

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_consumable_weapon_runtime_kind_keeps_weapon_executor_alive',
    '_check_csharp_attack_setup_is_not_gated_by_positive_damage',
    '_check_csharp_held_renderer_draws_non_weapon_generated_items',
    '_check_csharp_alt_use_tooltip_is_visible',
    '_check_attack_enabled_is_documented_as_generated_executor_not_can_damage',
    '_check_visual_manifest_distinguishes_runtime_executor_from_vanilla_hitbox',
    '_check_runtime_projectiles_use_single_hit_defaults_and_ignore_spawn_target_for_children'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_consumable_weapon_and_held_sprite_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
