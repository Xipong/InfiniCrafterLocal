from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch

VISUAL = server.visual_generation_pipeline


def test_incompatible_projectile_after_swing_recovers_as_secondary_not_deleted() -> None:
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
    assert patch["recoveredPrimaryConflictAsSecondary"]["mode"] == "swing_on_hit_secondary"
    assert patch["splitCount"] == 1
    assert patch["maxChildProjectiles"] == 1
    assert patch["secondaryProjectileShape"] == "splinter"
    assert patch["secondaryMaterial"] == "shadow"
    assert patch["secondaryDamageMultiplier"] > 0
    assert patch["onHit"] == "lifesteal"
    assert patch["secondaryPreservedAlongsidePrimaryOnHit"] == "lifesteal"


def test_compiled_swing_secondary_forces_child_sprite_not_main_projectile(monkeypatch) -> None:
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_PROJECTILE_IMAGES", True)
    monkeypatch.setattr(VISUAL, "VISUAL_GENERATE_CHILD_FIELD_IMAGES", True)
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

    plan = server.build_visual_asset_plan(data)
    projectile = next(x for x in plan if x["role"] == "projectile")
    child = next(x for x in plan if x["role"] == "child")

    assert projectile["assetMode"] == "particle_vfx"
    assert projectile["status"] == "skipped_not_authored_baked"
    assert child["assetMode"] == "baked_sprite"
    assert "status" not in child or not str(child.get("status", "")).startswith("skipped")


def test_hold_light_does_not_synthesize_fake_alt_use() -> None:
    source = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.Normalize.cs"
    text = source.read_text(encoding="utf-8")
    assert 'Gameplay.AltUseMode = "light"' not in text
    assert "Held light is passive" in text


def test_refit_helper_can_salvage_too_small_projectile_sprite(tmp_path, monkeypatch) -> None:
    if VISUAL.Image is None:
        return
    monkeypatch.setattr(VISUAL, "SPRITE_DIR", tmp_path)
    path = tmp_path / "tiny.png"
    img = VISUAL.Image.new("RGBA", (48, 48), (0, 0, 0, 0))
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

    refit = VISUAL.refit_processed_sprite_to_contract(str(path), "tiny_projectile", 48, "projectile", validation)

    assert refit
    assert Path(refit).exists()
    assert VISUAL.validate_processed_sprite(refit, "projectile")["ok"]


def test_single_variant_sprite_score_is_not_hardcoded_half() -> None:
    source = Path(__file__).resolve().parents[1] / "infini_local" / "pipelines" / "visual_generation_pipeline.py"
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


def test_burst_onhit_zero_cap_gets_minimum_visual_feedback() -> None:
    from infini_local.core.runtime_effect_policy import onhit_uses_burst_dust_feedback

    assert onhit_uses_burst_dust_feedback("burst", 1)
    assert onhit_uses_burst_dust_feedback("aura_pulse", 10)
    assert onhit_uses_burst_dust_feedback("lifesteal", 17)
    assert not onhit_uses_burst_dust_feedback("burn", 4)

    for on_hit, code in [("burst", 1), ("aura_pulse", 10), ("lifesteal", 17)]:
        sanitized = server.sanitize_genome_engine(_zero_cap_genome(on_hit, code), {"powerBudget": 1.0})
        assert sanitized["burstDustCap"] >= 4
        assert "burst_onhit_requires_nonzero_burstDustCap" in sanitized.get("engineSanityRepairs", [])

    burn = server.sanitize_genome_engine(_zero_cap_genome("burn", 4), {"powerBudget": 1.0})
    assert burn["burstDustCap"] == 0
    assert "burst_onhit_requires_nonzero_burstDustCap" not in burn.get("engineSanityRepairs", [])


def test_burst_onhit_policy_is_not_scattered_as_ad_hoc_magic_numbers() -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in ["infini_local/web/server.py", "infini_local/pipelines/pipeline_support.py"]:
        text = (root / rel).read_text(encoding="utf-8")
        assert "onhit_uses_burst_dust_feedback(onhit_key, onhit_code)" in text
        assert 'onhit_key in {"burst", "aura_pulse"}' not in text
        assert "onhit_code in {1, 10}" not in text

    csharp = (Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.Visuals.cs").read_text(encoding="utf-8")
    assert "private static bool OnHitUsesBurstDustFallback(int onHitCode)" in csharp
    assert "OnHitUsesBurstDustFallback(_spec.OnHitCode)" in csharp
