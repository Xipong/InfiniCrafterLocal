from __future__ import annotations

from pathlib import Path

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring.reports import runtime_plan_provenance_report

from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.item_power_knowledge import canonicalize

ROOT = Path(__file__).resolve().parents[2]

PARENT_BOW = {"name": "Daedalus Stormbow", "type": 1, "damage": 38, "useTime": 19, "value": 1000}
PARENT_ARROW = {"name": "Wooden Arrow", "type": 2, "damage": 5, "value": 10}


def _plan(family: str = "overhead_barrage", *, projectile_family: str = "arrow", effect: str = "none") -> dict:
    return {
        "name": "Skyline Volley",
        "tooltip": "Arrows descend over the aimed area.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "ranged",
                        "damage": 42,
                        "useTimeTicks": 28,
                    },
                },
                {
                    "fn": "fire_ranged_weapon",
                    "params": {
                        "family": family,
                        "ammoFor": "arrow",
                        "projectileFamily": projectile_family,
                        "projectileShape": "wooden arrow",
                        "effect": effect,
                        "speed": 11,
                        "shotCount": 4,
                        "spreadRadians": 0.25,
                        "pierce": 1,
                        "lifetimeTicks": 90,
                        "delayTicks": 12,
                        "rangeTiles": 55,
                        "secondaryDamageMultiplier": 0.35,
                        "secondaryLifetimeTicks": 60,
                    },
                },
            ],
        },
    }


def _contract_check_daedalus_like_ranged_authoring_keeps_delivery_and_theme_separate() -> None:
    data = _plan()
    patch = compile_runtime_plan_to_genome_patch(data)

    assert patch["runtimeFamily"] == "overhead_barrage"
    assert patch["delivery"] == "shoot"
    assert patch["weaponFamily"] == "ranged"
    assert patch["projectileFamily"] == "arrow"
    assert patch["projectileShape"] == "wooden arrow"
    assert patch["effect"] == "none"
    assert patch["ammoFor"] == "arrow"
    assert patch["shotCount"] == 4
    assert patch["delayTicks"] == 12
    assert patch["maxChildProjectiles"] == 4
    assert patch["maxChildDepth"] == 1


def _contract_check_daedalus_like_ranged_authoring_survives_full_pipeline() -> None:
    ca = canonicalize(PARENT_BOW)
    cb = canonicalize(PARENT_ARROW)
    child = validate_and_repair(_plan(), PARENT_BOW, PARENT_ARROW, ca, cb, "v11_daedalus_like")
    child = final_normalize(attach_gameplay_and_attack(child, PARENT_BOW, PARENT_ARROW, ca, cb))
    genome = child["attack"]["genome"]

    assert genome["runtimeFamily"] == "overhead_barrage"
    assert genome["projectileFamily"] == "arrow"
    assert genome["projectileShape"] == "wooden arrow"
    assert genome["effect"] == "none"
    assert child["attack"]["ammoKind"] == "arrow"
    assert child["gameplay"]["ammoFor"] == "arrow"
    assert genome["shotCount"] == 4
    assert genome["delayTicks"] == 12


def _contract_check_removed_family_token_and_names_do_not_select_gameplay() -> None:
    unknown = compile_runtime_plan_to_genome_patch(_plan("unknown_delivery_family", projectile_family="ice_shard"))
    assert unknown["runtimeFamily"] == "shoot"
    assert unknown["projectileFamily"] == "ice_shard"
    assert "delayTicks" not in unknown

    ordinary = _plan("starfall_bow")
    ordinary["name"] = "Starfall Bow"
    ordinary["tooltip"] = "A bow decorated with stars."
    patch = compile_runtime_plan_to_genome_patch(ordinary)
    assert patch["runtimeFamily"] == "shoot"
    assert patch["projectileFamily"] == "arrow"


def _contract_check_overhead_barrage_provenance_marks_authored_projectile_identity() -> None:
    data = _plan()
    patch = compile_runtime_plan_to_genome_patch(data)
    report = runtime_plan_provenance_report(data, patch)

    for field in (
        "runtimeFamily",
        "projectileFamily",
        "projectileShape",
        "ammoFor",
        "effect",
        "shotCount",
        "delayTicks",
        "rangeTiles",
    ):
        assert report["authoredFields"][field] is True, field
        assert report["fieldSources"][field] == "fire_ranged_weapon", field

    assert report["gameplayChildren"]["source"] == "overhead_barrage"
    assert report["gameplayChildren"]["overheadBarrageChildEstimate"] == 4


def _contract_check_csharp_executor_configures_geometry_without_forcing_star_theme() -> None:
    policy_path = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedOverheadBarragePolicy.cs"
    executor_path = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.OverheadBarrage.cs"
    old_policy = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedDelayedStarfallPolicy.cs"
    old_executor = ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.DelayedStarfall.cs"

    policy = policy_path.read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")

    assert policy_path.exists() and executor_path.exists()
    assert not old_policy.exists() and not old_executor.exists()
    assert "child.TileCollide = parent.TileCollide" in policy
    assert "parent.ProjectileFamily" in policy
    assert "parent.ProjectileShape" in policy
    assert "EffectCode = 3" not in policy
    assert "falling_star" not in policy.lower()
    assert "falling star" not in policy.lower()
    assert "SpawnOverheadBarrage" in impact
    assert "SpawnGeneratedSwingOverheadBarrage" in item


def _starfury_plan(*, family: str = "overhead_barrage") -> dict:
    return {
        "name": "Astral Edge",
        "tooltip": "A melee swing calls an authored star down from above.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "melee",
                        "damage": 34,
                        "useTimeTicks": 22,
                    },
                },
                {
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": family,
                        "delivery": "swing",
                        "movement": "straight",
                        "weaponFamily": "broadsword",
                        "projectileFamily": "star",
                        "projectileShape": "five-point falling star",
                        "effect": "star",
                        "speed": 12,
                        "shotCount": 1,
                        "spreadRadians": 0.0,
                        "pierce": 1,
                        "lifetimeTicks": 90,
                        "delayTicks": 0,
                        "rangeTiles": 50,
                    },
                },
            ],
        },
    }


def _contract_check_starfury_like_swing_keeps_authored_star_theme_and_zero_delay() -> None:
    patch = compile_runtime_plan_to_genome_patch(_starfury_plan())

    assert patch["runtimeFamily"] == "overhead_barrage"
    assert patch["delivery"] == "swing"
    assert patch["useStyleCode"] == 1
    assert patch["hideUseGraphic"] is False
    assert patch["disableItemMeleeHitbox"] is False
    assert patch["projectileFamily"] == "star"
    assert patch["projectileShape"] == "five-point falling star"
    assert patch["effect"] == "star"
    assert patch["delayTicks"] == 0
    assert patch["soundUseCatalogId"] == "melee_swing"
    assert patch["soundImpactCatalogId"] == "impact_star"


def _contract_check_starfury_like_star_theme_survives_full_pipeline() -> None:
    parent_a = {"name": "Gold Broadsword", "type": 1, "damage": 13, "useTime": 21, "value": 1000}
    parent_b = {"name": "Fallen Star", "type": 75, "damage": 0, "value": 500}
    ca = canonicalize(parent_a)
    cb = canonicalize(parent_b)
    child = validate_and_repair(_starfury_plan(), parent_a, parent_b, ca, cb, "v11_starfury_like")
    child = final_normalize(attach_gameplay_and_attack(child, parent_a, parent_b, ca, cb))
    genome = child["attack"]["genome"]
    assert child["gameplay"]["damageClass"] == "melee"
    assert genome["runtimeFamily"] == "overhead_barrage"
    assert genome["delivery"] == "swing"
    assert genome["useStyleCode"] == 1
    assert genome["disableItemMeleeHitbox"] is False
    assert genome["projectileFamily"] == "star"
    assert genome["projectileShape"] == "five-point falling star"
    assert genome["effect"] == "star"
    assert genome["delayTicks"] == 0


def _contract_check_overhead_barrage_csharp_preserves_effect_and_selects_item_affordance_from_delivery() -> None:
    family_policy = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedRuntimeFamilyPolicy.cs").read_text(encoding="utf-8")
    apply_source = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs").read_text(encoding="utf-8")
    child_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    barrage_policy = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedOverheadBarragePolicy.cs").read_text(encoding="utf-8")

    assert "UsesProjectileOnlyItemAffordance" in family_policy
    assert 'family == OverheadBarrage && carrier == "swing"' in family_policy
    assert "UsesProjectileOnlyItemAffordance(runtimeFamily, Attack.Delivery)" in apply_source
    assert "EffectCode = _spec.EffectCode" in child_runtime
    assert "child.EffectCode =" not in barrage_policy
    assert "parent.ProjectileFamily" in barrage_policy
    assert "parent.ProjectileShape" in barrage_policy


def _contract_check_llm_repair_prompt_advertises_only_canonical_overhead_name() -> None:
    repair_source = (ROOT / "LocalGenerator/infini_local/pipelines/combine_genome.py").read_text(encoding="utf-8")
    assert "starburst|overhead_barrage|aura_pulse" in repair_source
    assert "starburst|starfall|aura_pulse" not in repair_source


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_v11_overhead_barrage_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_daedalus_like_ranged_authoring_keeps_delivery_and_theme_separate',
            '_contract_check_daedalus_like_ranged_authoring_survives_full_pipeline',
            '_contract_check_removed_family_token_and_names_do_not_select_gameplay',
            '_contract_check_overhead_barrage_provenance_marks_authored_projectile_identity',

            '_contract_check_csharp_executor_configures_geometry_without_forcing_star_theme',
            '_contract_check_starfury_like_swing_keeps_authored_star_theme_and_zero_delay',
            '_contract_check_starfury_like_star_theme_survives_full_pipeline',
            '_contract_check_overhead_barrage_csharp_preserves_effect_and_selects_item_affordance_from_delivery',
            '_contract_check_llm_repair_prompt_advertises_only_canonical_overhead_name',
        ),
    )
