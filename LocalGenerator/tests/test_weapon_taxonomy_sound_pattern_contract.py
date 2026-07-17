from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.item_power_knowledge import canonicalize
from infini_local.pipelines import presentation_sound

from csharp_partial_reader import read_text_with_partial_bundles

PARENT_A = {"name": "Shotgun", "type": 534, "damage": 24, "useTime": 45, "value": 1000}
PARENT_B = {"name": "Fallen Star", "type": 75, "damage": 0, "value": 100}


def _compile(plan: dict, key: str) -> dict:
    ca = canonicalize(PARENT_A)
    cb = canonicalize(PARENT_B)
    child = validate_and_repair(plan, PARENT_A, PARENT_B, ca, cb, key)
    child = final_normalize(attach_gameplay_and_attack(child, PARENT_A, PARENT_B, ca, cb))
    attack = child["attack"]
    return attack.get("genome") if isinstance(attack.get("genome"), dict) else attack


def _contract_check_auxiliary_weapon_taxonomy_is_not_part_of_runtime_contract() -> None:
    plan = {
        "name": "Starfall Scattergun",
        "tooltip": "A shotgun that bursts into falling star pellets.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 32, "useTimeTicks": 38}},
                {"fn": "fire_ranged_weapon", "params": {
                    "family": "shotgun",
                    "ammoFor": "bullet",
                    "movement": "gravity_arc",
                    "speed": 11,
                    "rangeTiles": 48,
                    "lifetimeTicks": 90,
                    "pierce": 1,
                    "shotCount": 5,
                    "spreadRadians": 0.35,
                    "projectileShape": "small star pellets",
                    "projectileImpact": "sparkling falling star burst",
                }},
                {"fn": "spawn_contact_particles", "params": {"effect": "star", "amount": 16, "scale": 0.9}},
            ],
        },
    }

    genome = _compile(plan, "taxonomy_removed")
    assert genome["weaponFamily"] == "shotgun"
    assert genome["runtimeFamily"] == "shoot"
    assert "weaponSubfamily" not in genome
    assert "attackPatternTags" not in genome
    assert genome["soundUseCatalogId"] == "firearm_light"
    assert genome["soundImpactCatalogId"] == "impact_star"
    assert genome["soundCatalogSource"] == "terraria_vanilla"


def _contract_check_overhead_visual_role_uses_exact_runtime_fields_without_tags() -> None:
    plan = {
        "name": "Falling Star Saber",
        "tooltip": "A broadsword slash calls down bounded falling stars.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 28, "useTimeTicks": 32}},
                {"fn": "perform_melee_attack", "params": {"family": "broadsword", "projectileShape": "wide golden star slash arc", "effect": "star", "speed": 8, "rangeTiles": 5, "lifetimeTicks": 24, "shotCount": 1, "spreadRadians": 0.0, "pierce": 1}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "overhead_barrage", "count": 4, "aoeRadiusTiles": 2}},
            ],
        },
    }

    genome = _compile(plan, "overhead_no_tags")
    assert genome["runtimeFamily"] == "swing"
    assert genome["onHit"] == "overhead_barrage"
    assert genome["splitCount"] == 4
    assert "attackPatternTags" not in genome


def _contract_check_runtime_color_is_exact_effect_derived_not_mode_or_visual_palette() -> None:
    def payload(effect: str, primary: str = "") -> dict:
        return {
            "runtimePlan": {"engineCalls": [{"fn": "set_item_stats", "params": {}}]},
            "attack": {"enabled": True, "effect": effect, "primaryColorName": primary},
            "presentationGenome": {"palette": ["white_gold"], "projectileVisual": {"color": "toxic_green"}},
        }

    assert presentation_sound.attach_presentation_and_sound(payload("none"))["attack"]["primaryColorName"] == "white"
    assert presentation_sound.attach_presentation_and_sound(payload("star"))["attack"]["primaryColorName"] == "gold"
    assert presentation_sound.attach_presentation_and_sound(payload("electric", "cyan"))["attack"]["primaryColorName"] == "cyan"
    assert presentation_sound.attach_presentation_and_sound(payload("electric", "white_gold"))["attack"]["primaryColorName"] == "cyan"

def _contract_check_csharp_contract_has_no_auxiliary_taxonomy_or_sound_text_router() -> None:
    root = Path(__file__).resolve().parents[2]
    model = read_text_with_partial_bundles(root / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.cs")
    sound = (root / "ModSources/InfiniCrafterLocal/Common/Audio/InfiniSoundLibrary.cs").read_text(encoding="utf-8")
    projectile = read_text_with_partial_bundles(root / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.cs")

    for removed in ["WeaponSubfamily", "AttackPatternTags", "SoundUseSearchQuery", "SoundImpactSearchQuery"]:
        assert removed not in model
    for forbidden in ["starfury", "enchanted_sword", "water_bolt", "last_prism", "stardust_dragon", "StyleFromRangedText", "HasAny"]:
        assert forbidden not in sound
    for exact_id in ["shotgun_heavy", "magic_spectral", "summon_portal", "impact_star"]:
        assert f'["{exact_id}"]' in sound
    impact_method = projectile.split("private void PlayImpactSound", 1)[1].split("public override void OnKill", 1)[0]
    assert "WeaponFamily" not in impact_method
    assert "ProjectileFamily" not in impact_method


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_weapon_taxonomy_sound_pattern_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_auxiliary_weapon_taxonomy_is_not_part_of_runtime_contract',
            '_contract_check_overhead_visual_role_uses_exact_runtime_fields_without_tags',
            '_contract_check_runtime_color_is_exact_effect_derived_not_mode_or_visual_palette',
            '_contract_check_csharp_contract_has_no_auxiliary_taxonomy_or_sound_text_router',
        ),
    )
