from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.web import server


from csharp_partial_reader import read_text_with_partial_bundles
PARENT_A = {"name": "Shotgun", "type": 534, "damage": 24, "useTime": 45, "value": 1000}
PARENT_B = {"name": "Fallen Star", "type": 75, "damage": 0, "value": 100}


def test_runtime_plan_preserves_weapon_subfamily_attack_tags_and_sound_queries() -> None:
    plan = {
        "name": "Starfall Scattergun",
        "tooltip": "A shotgun that bursts into falling star pellets.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 32, "useTimeTicks": 38, "weaponSubfamily": "shotgun"}},
                {"fn": "fire_ranged_weapon", "params": {
                    "family": "shotgun",
                    "ammoFor": "bullet",
                    "movement": "gravity_arc",
                    "shotCount": 5,
                    "spreadRadians": 0.35,
                    "projectileShape": "small star pellets",
                    "projectileImpact": "sparkling falling star burst",
                    "weaponSubfamily": "shotgun",
                    "attackPatternTags": ["shotgun_spread", "falling_star"],
                }},
                {"fn": "spawn_contact_particles", "params": {"effect": "star", "amount": 16, "scale": 0.9}},
            ],
        },
    }

    child = server.final_normalize(server.validate_and_repair(plan, PARENT_A, PARENT_B, {}, {}, "taxonomy_sound"))
    attack = child["attack"]
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else attack
    assert genome["weaponFamily"] == "shotgun"
    assert genome["weaponSubfamily"] == "shotgun"
    assert "shotgun_spread" in genome["attackPatternTags"]
    assert "falling_star" in genome["attackPatternTags"]
    assert "shotgun" in genome["soundUseSearchQuery"]
    assert "falling star" in genome["soundImpactSearchQuery"]
    assert genome["runtimeFamily"] == "shoot"


def test_slash_text_does_not_false_positive_as_whip_lash_tag() -> None:
    plan = {
        "name": "Falling Star Saber",
        "tooltip": "A broadsword slash calls down bounded falling stars.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 28, "useTimeTicks": 32}},
                {"fn": "perform_melee_attack", "params": {"family": "broadsword", "projectileShape": "wide golden star slash arc", "effect": "star"}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "starfall", "count": 4, "aoeRadiusTiles": 2}},
            ],
        },
    }

    child = server.final_normalize(server.validate_and_repair(plan, PARENT_A, PARENT_B, {}, {}, "slash_not_whip"))
    attack = child["attack"]
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else attack
    tags = set(genome.get("attackPatternTags") or [])
    assert "falling_star" in tags
    assert "whip_lash" not in tags
    assert "whip lash" not in str(genome.get("soundUseSearchQuery") or "").lower()
    assert "whip lash" not in str(genome.get("soundImpactSearchQuery") or "").lower()


def test_csharp_model_and_sound_catalog_preserve_taxonomy_surface() -> None:
    root = Path(__file__).resolve().parents[2]
    model = read_text_with_partial_bundles(root / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.cs")
    sound = (root / "ModSources/InfiniCrafterLocal/Common/Audio/InfiniSoundLibrary.cs").read_text(encoding="utf-8")
    projectile = read_text_with_partial_bundles(root / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.cs")
    for needle in ["WeaponSubfamily", "AttackPatternTags", "SoundUseSearchQuery", "SoundImpactSearchQuery"]:
        assert needle in model
    for needle in ["starfury", "enchanted_sword", "water_bolt", "last_prism", "phantasm", "stardust_dragon"]:
        assert needle in sound
    assert "_spec.WeaponSubfamily" in projectile
    assert "_spec.AttackPatternTags" in projectile
