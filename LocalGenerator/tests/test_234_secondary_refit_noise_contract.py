from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core import image_dependencies as IMAGE_DEPS
from infini_local.pipelines import visual_asset_plan as ASSET_PLAN
from infini_local.pipelines import visual_sprite_generation as SPRITES
from infini_local.pipelines.engine_pressure_metrics import sanitize_genome_engine
from infini_local.pipelines.sprite_postprocess import validate_processed_sprite
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch


def _contract_check_incompatible_projectile_after_swing_is_rejected_without_semantic_salvage() -> None:
    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 18, "useTimeTicks": 24}},
                {"fn": "perform_melee_attack", "params": {"family": "broadsword", "speed": 12, "rangeTiles": 4}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 10, "rangeTiles": 12, "lifetimeTicks": 40, "projectileShape": "splinter", "projectileTrail": "shadow", "damageMultiplier": 0.25}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "lifesteal"}},
            ]
        },
    }

    patch = compile_runtime_plan_to_genome_patch(data)

    assert patch["runtimeFamily"] == "swing"
    assert patch["delivery"] == "swing"
    assert patch["rejectedPrimaryCalls"][0]["reason"] == "runtime_one_primary_family"
    assert "recoveredPrimaryConflictAsSecondary" not in patch
    assert "secondaryProjectileShape" not in patch
    assert patch["onHit"] == "lifesteal"


def _contract_check_compiled_swing_secondary_keeps_visual_director_child_mode(monkeypatch) -> None:
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)
    monkeypatch.setattr(ASSET_PLAN, "VISUAL_GENERATE_CHILD_FIELD_IMAGES", True)
    data = {
        "id": "shadowbrand",
        "category": "weapon",
        "runtimePlan": {"engineCalls": [{"fn": "set_item_stats", "params": {"resultKind": "weapon"}}]},
        "attack": {
            "enabled": True,
            "runtimeFamily": "swing",
            "delivery": "swing",
            "disableItemMeleeHitbox": False,
            "splitCount": 1,
            "maxChildProjectiles": 1,
            "secondaryProjectileShape": "splinter",
            "secondaryMaterial": "shadow",
        },
        "visual": {"imagePrompt": "dark blade", "projectileImagePrompt": "main projectile should be skipped"},
        "visualKit": {
            "bakedAssets": {
                "projectile": {"mode": "baked_sprite", "prompt": "main projectile should be skipped"},
                "child": {"mode": "particle_vfx", "prompt": "small shadow splinter"},
            }
        },
    }

    plan = build_visual_asset_plan(data)
    projectile = next(x for x in plan if x["role"] == "projectile")
    child = next(x for x in plan if x["role"] == "child")

    assert projectile["assetMode"] == "particle_vfx"
    assert projectile["status"] == "skipped_not_authored_baked"
    assert child["assetMode"] == "particle_vfx"
    assert child["status"] == "skipped_not_authored_baked"


def _contract_check_hold_light_does_not_synthesize_fake_alt_use() -> None:
    source = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.Normalize.cs"
    text = source.read_text(encoding="utf-8")
    assert 'Gameplay.AltUseMode = "light"' not in text
    assert "Held light is passive" in text


def _contract_check_refit_helper_can_salvage_too_small_projectile_sprite(tmp_path, monkeypatch) -> None:
    if IMAGE_DEPS.Image is None:
        return
    monkeypatch.setattr(SPRITES, "SPRITE_DIR", tmp_path)
    path = tmp_path / "tiny.png"
    img = IMAGE_DEPS.Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    for x in range(18, 30):
        for y in range(18, 30):
            img.putpixel((x, y), (80, 20, 120, 255))
    img.save(path)
    validation = {
        "ok": False,
        "reasons": ["core_silhouette_too_small:12px<32px"],
        "stats": {"bbox": [18, 18, 30, 30]},
        "bboxStats": {
            "core_bbox": [18, 18, 30, 30],
            "spec": {"targetLongAxisPx": 40, "marginPx": 2},
        },
    }

    refit = SPRITES.refit_processed_sprite_to_contract(str(path), "tiny_projectile", 48, "projectile", validation)

    assert refit
    assert Path(refit).exists()
    assert validate_processed_sprite(refit, "projectile")["ok"]


def _contract_check_refit_helper_can_salvage_too_small_item_sprite(tmp_path, monkeypatch) -> None:
    if IMAGE_DEPS.Image is None:
        return
    monkeypatch.setattr(SPRITES, "SPRITE_DIR", tmp_path)
    path = tmp_path / "tiny_item.png"
    img = IMAGE_DEPS.Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    for x in range(21, 27):
        for y in range(12, 36):
            img.putpixel((x, y), (210, 210, 80, 255))
    img.save(path)
    validation = {
        "ok": False,
        "reasons": ["core_silhouette_too_small:24px<39px"],
        "stats": {"bbox": [21, 12, 27, 36]},
        "bboxStats": {
            "core_bbox": [21, 12, 27, 36],
            "spec": {"targetLongAxisPx": 44, "marginPx": 2},
        },
    }

    refit = SPRITES.refit_processed_sprite_to_contract(str(path), "tiny_item", 48, "item", validation)

    assert refit
    assert Path(refit).exists()
    assert validate_processed_sprite(refit, "item")["ok"]


def _contract_check_item_sprite_generation_runs_refit_before_accepting_too_small_sprite() -> None:
    source = Path(__file__).resolve().parents[1] / "infini_local" / "pipelines" / "visual_sprite_generation.py"
    text = source.read_text(encoding="utf-8")
    item_block = text[text.index("def maybe_generate_sprite"):text.index("def _validation_reasons")]
    assert 'refit_processed_sprite_to_contract(final_path, attempt_id, canvas, "item", validation)' in item_block
    assert 'debug", {})["itemSpriteRefit"]' in item_block


def _contract_check_single_variant_sprite_score_is_not_hardcoded_half() -> None:
    source = Path(__file__).resolve().parents[1] / "infini_local" / "pipelines" / "visual_sprite_generation.py"
    text = source.read_text(encoding="utf-8")
    assert "else (variants[0], 0.5)" not in text
    assert 'best, score = pick_best_sprite(variants, "item", canvas)' in text
    assert "best, score = pick_best_sprite(variants, role, canvas)" in text


def _zero_cap_genome(on_hit: str, on_hit_code: int) -> dict:
    return {
        "runtimeFamily": "shoot",
        "delivery": "shoot",
        "movement": "straight",
        "movementCode": 0,
        "effect": "dust",
        "effectCode": 0,
        "onHit": on_hit,
        "onHitCode": on_hit_code,
        "shotCount": 1,
        "lifetimeTicks": 30,
        "extraUpdates": 0,
        "splitCount": 0,
        "chainCount": 0,
        "burstDustCap": 0,
    }


def _contract_check_burst_onhit_zero_cap_stays_zero() -> None:
    for on_hit, code in [("burst", 1), ("aura_pulse", 10), ("lifesteal", 17), ("burn", 4)]:
        sanitized = sanitize_genome_engine(_zero_cap_genome(on_hit, code), {"powerBudget": 1.0})
        assert sanitized["burstDustCap"] == 0
        assert "burst_onhit_requires_nonzero_burstDustCap" not in sanitized.get("engineSanityRepairs", [])


def _contract_check_burst_visual_feedback_has_no_hidden_policy_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    engine_metrics = (root / "infini_local/pipelines/engine_pressure_metrics.py").read_text(encoding="utf-8")
    assert "onhit_uses_burst_dust_feedback" not in engine_metrics
    csharp = (Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Visuals.cs").read_text(encoding="utf-8")
    assert "OnHitUsesBurstDustFallback" not in csharp
    assert "count = Math.Clamp(count, 0, authoredCap)" in csharp


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_234_secondary_refit_noise_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_incompatible_projectile_after_swing_is_rejected_without_semantic_salvage',
            '_contract_check_compiled_swing_secondary_keeps_visual_director_child_mode',
            '_contract_check_hold_light_does_not_synthesize_fake_alt_use',
            '_contract_check_refit_helper_can_salvage_too_small_projectile_sprite',
            '_contract_check_refit_helper_can_salvage_too_small_item_sprite',
            '_contract_check_item_sprite_generation_runs_refit_before_accepting_too_small_sprite',
            '_contract_check_single_variant_sprite_score_is_not_hardcoded_half',
            '_contract_check_burst_onhit_zero_cap_stays_zero',
            '_contract_check_burst_visual_feedback_has_no_hidden_policy_owner',
        ),
    )
