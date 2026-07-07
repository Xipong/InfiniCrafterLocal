from __future__ import annotations

from infini_local.pipelines.combine_pipeline import apply_accessory_soft_budget, apply_armor_soft_budget


def _stage() -> dict[str, object]:
    return {"powerBudget": 2.2, "rarity": 3, "parentGeneratedDepths": [1]}


def test_accessory_total_budget_clamps_all_in_one_stats() -> None:
    stats = {
        "enabled": True,
        "genericDamage": 0.35,
        "meleeDamage": 0.24,
        "rangedDamage": 0.24,
        "magicDamage": 0.24,
        "summonDamage": 0.24,
        "genericCrit": 18,
        "movementSpeed": 0.45,
        "endurance": 0.28,
        "manaCostReduction": 0.3,
        "ammoSaveChance": 0.35,
        "minionSlots": 3,
        "sentrySlots": 2,
        "lavaImmune": True,
    }

    final, report = apply_accessory_soft_budget(stats, _stage())

    assert report["clamps"]
    assert "total_stat_budget" in report["reasons"]
    assert "endurance_pressure" in report["reasons"]
    assert "all_in_one_accessory" in report["reasons"]
    assert report["finalCost"] < report["rawCost"]
    assert final["genericDamage"] < stats["genericDamage"]


def test_moderate_accessory_budget_is_unchanged() -> None:
    stats = {"enabled": True, "movementSpeed": 0.12, "jumpSpeed": 0.08, "fallDamageImmune": True}
    final, report = apply_accessory_soft_budget(stats, _stage())
    assert final == stats
    assert report["clamps"] == []


def test_armor_piece_and_set_bonus_have_separate_budget_reports() -> None:
    stats = {
        "enabled": True,
        "slot": "body",
        "defense": 42,
        "genericDamage": 0.32,
        "movementSpeed": 0.3,
        "endurance": 0.22,
        "setBonusGenericDamage": 0.42,
        "setBonusMovementSpeed": 0.35,
        "setBonusMinionSlots": 3,
    }

    final, report = apply_armor_soft_budget(stats, _stage(), "body")

    assert report["clamps"]
    assert "total_stat_budget" in report["reasons"]
    assert "set_bonus_pressure" in report["reasons"]
    assert final["defense"] <= stats["defense"]
    assert final["setBonusGenericDamage"] < stats["setBonusGenericDamage"]
