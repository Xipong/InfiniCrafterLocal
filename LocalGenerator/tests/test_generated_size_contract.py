from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs"
ITEM = ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs"
PROJECTILE = ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs"
HELD_LAYER = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "GeneratedHeldItemDrawLayer.cs"


def _check_generated_item_runtime_size_clamps_are_terraria_sized() -> None:
    src = read_text_with_partial_bundles(MODEL)
    assert "Gameplay.Width = ClampInt(Gameplay.Width, 8, 64)" in src
    assert "Gameplay.Height = ClampInt(Gameplay.Height, 8, 64)" in src
    assert "Gameplay.ItemScale = ClampFloat(Gameplay.ItemScale, 0.55f, 1.55f)" in src
    assert "Gameplay.HealLife = ClampInt(Gameplay.HealLife, 0, 500)" in src
    assert "Gameplay.HealMana = ClampInt(Gameplay.HealMana, 0, 500)" in src
    assert "Gameplay.BuffCode = ClampInt(Gameplay.BuffCode, InfiniTerrariaSentinels.NoBuffType, 1024)" in src
    assert "Gameplay.PickPower = ClampInt(Gameplay.PickPower, 0, 230)" in src
    assert "Gameplay.AxePower = ClampInt(Gameplay.AxePower, 0, 50)" in src
    assert "Gameplay.HammerPower = ClampInt(Gameplay.HammerPower, 0, 120)" in src
    assert "Visual.InventoryScale = ClampFloat(Visual.InventoryScale, 0.55f, 1.55f)" in src
    assert "Visual.WorldScale = ClampFloat(Visual.WorldScale, 0.55f, 1.75f)" in src
    assert "Attack.ProjectileWidth = ClampInt(Attack.ProjectileWidth, 4, 96)" in src
    assert "Attack.ProjectileHeight = ClampInt(Attack.ProjectileHeight, 4, 96)" in src
    assert "Attack.ProjectileScale = ClampFloat(Attack.ProjectileScale, 0.35f, 2.25f)" in src
    assert "Attack.HitboxScale = ClampFloat(Attack.HitboxScale, 0.5f, 2.5f)" in src
    assert "Attack.ExplosionRadius = ClampInt(Attack.ExplosionRadius, 0, 128)" in src
    assert "4096" not in src
    assert "ClampFloat(Gameplay.ItemScale, 0.05f, 10f)" not in src


def _check_held_draw_does_not_double_apply_item_scale() -> None:
    src = HELD_LAYER.read_text(encoding="utf-8")
    assert "GetAdjustedItemScale" in src
    assert "Do not multiply by Gameplay.ItemScale again" in src
    assert "baseScale * itemScale" not in src
    assert "Math.Clamp(baseScale * payloadScale, 0.45f, 1.85f)" in src


def _check_world_draw_anchors_scaled_sprite_bottom_and_clamps_visual_scales() -> None:
    src = ITEM.read_text(encoding="utf-8")
    assert "Math.Clamp(Data.Visual.InventoryScale, 0.55f, 1.55f)" in src
    assert "Math.Clamp(Data.Visual.WorldScale, 0.55f, 1.75f)" in src
    assert "drawOrigin.Y * finalScale" in src
    assert "drawOrigin.Y);" not in src


def _check_melee_explosion_radius_no_longer_becomes_half_radius_hidden_reach() -> None:
    src = ITEM.read_text(encoding="utf-8")
    assert "MeleeHitboxRadiusBonus" in src
    assert "attack.ContactForgivenessPx" in src and "attack.AoeDamageRadiusPx / 6" in src
    assert "ExplosionRadius / 2" not in src


def _check_projectile_runtime_size_is_sanitized_before_apply_and_hitbox_radius_is_capped() -> None:
    src = read_text_with_partial_bundles(PROJECTILE)
    assert "SanitizeRuntimeSize(_spec)" in src
    assert "ProjectileWidth = Math.Clamp" in src
    assert "ResizeProjectilePreserveCenter(Math.Clamp(_spec.ProjectileWidth, 8, 96)" in src
    assert "Projectile.scale = Math.Clamp(_spec.ProjectileScale, 0.45f, 2.25f)" in src
    assert "ProjectileHitboxRadiusBonus" in src
    assert "_spec.ContactForgivenessPx" in src and "_spec.AoeDamageRadiusPx / 4" in src
    assert "ExplosionRadius / 2" not in src

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_generated_item_runtime_size_clamps_are_terraria_sized',
    '_check_held_draw_does_not_double_apply_item_scale',
    '_check_world_draw_anchors_scaled_sprite_bottom_and_clamps_visual_scales',
    '_check_melee_explosion_radius_no_longer_becomes_half_radius_hidden_reach',
    '_check_projectile_runtime_size_is_sanitized_before_apply_and_hitbox_radius_is_capped'
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


def test_generated_size_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
