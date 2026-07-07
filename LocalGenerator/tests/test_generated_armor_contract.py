from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.web import server


from csharp_partial_reader import read_text_with_partial_bundles
PARENT_A = {"name": "Iron Helmet", "type": 90, "defense": 2, "value": 100}
PARENT_B = {"name": "Cloud in a Bottle", "type": 53, "value": 100}


def test_generated_armor_runtime_plan_preserves_full_armor_property_surface() -> None:
    armor_params = {
        "armorSlot": "head",
        "setKey": "cloudforged",
        "archetype": "mobility",
        "defense": 5,
        "maxLife": 20,
        "maxMana": 10,
        "lifeRegen": 1,
        "manaRegen": 2,
        "movementSpeed": 0.08,
        "maxRunSpeed": 0.12,
        "jumpSpeed": 0.5,
        "genericDamage": 0.03,
        "meleeDamage": 0.04,
        "rangedDamage": 0.05,
        "magicDamage": 0.06,
        "summonDamage": 0.07,
        "genericCrit": 3,
        "attackSpeed": 0.02,
        "knockback": 0.1,
        "fallDamageImmune": True,
        "lavaImmune": True,
        "waterWalk": True,
        "minionSlots": 1,
        "sentrySlots": 1,
        "manaCostReduction": 0.08,
        "ammoSaveChance": 0.25,
        "aggro": -120,
        "endurance": 0.06,
        "armorPenetration": 5,
        "whipRange": 0.2,
        "summonTagDamage": 0.15,
        "lightStrength": 0.4,
        "lightColorName": "sky",
        "setBonusText": "Cloudforged set bonus",
        "setBonusGenericDamage": 0.02,
        "setBonusMeleeDamage": 0.03,
        "setBonusRangedDamage": 0.04,
        "setBonusMagicDamage": 0.05,
        "setBonusSummonDamage": 0.06,
        "setBonusGenericCrit": 2,
        "setBonusMovementSpeed": 0.1,
        "setBonusLifeRegen": 1,
        "setBonusManaRegen": 2,
        "setBonusMinionSlots": 1,
        "setBonusSentrySlots": 1,
        "setBonusManaCostReduction": 0.05,
        "setBonusAmmoSaveChance": 0.2,
        "setBonusAggro": -80,
        "setBonusEndurance": 0.05,
        "setBonusArmorPenetration": 4,
    }
    plan = {
        "name": "Cloudforged Helm",
        "tooltip": "A light helmet that keeps its generated armor stats.",
        "category": "armor",
        "runtimePlan": {
            "resultKind": "armor",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "armor", "armorSlot": "head", "rarity": 2, "value": 500}},
                {"fn": "armor_effect", "params": armor_params},
            ],
        },
    }

    child = server.final_normalize(server.validate_and_repair(plan, PARENT_A, PARENT_B, {}, {}, "armor_smoke"))

    assert child["category"] == "armor"
    assert child["gameplay"]["kind"] == "armor"
    assert child["gameplay"].get("damage", 0) == 0
    assert child["gameplay"].get("maxStack", 1) == 1
    assert child["armor"]["enabled"] is True
    assert child["armor"]["slot"] == "head"
    for key, value in {
        "setKey": "cloudforged",
        "archetype": "mobility",
        "defense": 5,
        "maxLife": 20,
        "maxMana": 10,
        "lifeRegen": 1,
        "manaRegen": 2,
        "movementSpeed": 0.08,
        "maxRunSpeed": 0.12,
        "jumpSpeed": 0.5,
        "genericDamage": 0.03,
        "meleeDamage": 0.04,
        "rangedDamage": 0.05,
        "magicDamage": 0.06,
        "summonDamage": 0.07,
        "genericCrit": 3.0,
        "attackSpeed": 0.02,
        "knockback": 0.1,
        "fallDamageImmune": True,
        "lavaImmune": True,
        "waterWalk": True,
        "minionSlots": 1,
        "sentrySlots": 1,
        "manaCostReduction": 0.08,
        "ammoSaveChance": 0.25,
        "aggro": -120,
        "endurance": 0.06,
        "armorPenetration": 5,
        "whipRange": 0.2,
        "summonTagDamage": 0.15,
        "lightStrength": 0.4,
        "lightColorName": "sky",
        "setBonusText": "Cloudforged set bonus",
        "setBonusGenericDamage": 0.02,
        "setBonusMeleeDamage": 0.03,
        "setBonusRangedDamage": 0.04,
        "setBonusMagicDamage": 0.05,
        "setBonusSummonDamage": 0.06,
        "setBonusGenericCrit": 2.0,
        "setBonusMovementSpeed": 0.1,
        "setBonusLifeRegen": 1,
        "setBonusManaRegen": 2,
        "setBonusMinionSlots": 1,
        "setBonusSentrySlots": 1,
        "setBonusManaCostReduction": 0.05,
        "setBonusAmmoSaveChance": 0.2,
        "setBonusAggro": -80,
        "setBonusEndurance": 0.05,
        "setBonusArmorPenetration": 4.0,
    }.items():
        assert child["armor"].get(key) == value


def test_csharp_generated_armor_proxy_surface_is_static_guarded() -> None:
    root = Path(__file__).resolve().parents[2]
    model = read_text_with_partial_bundles(root / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.cs")
    item = (root / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    proxy = (root / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedArmorItems.cs").read_text(encoding="utf-8")
    player = read_text_with_partial_bundles(root / "ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs")
    for needle in ["[AutoloadEquip(EquipType.Head)]", "[AutoloadEquip(EquipType.Body)]", "[AutoloadEquip(EquipType.Legs)]"]:
        assert needle in proxy
    for needle in ["public ArmorSpec Armor", "item.defense = Math.Max(0, Armor.Defense)", "NormalizeArmorSlot"]:
        assert needle in model
    for needle in ["UpdateEquip", "IsArmorSet", "UpdateArmorSet", "ApplyGeneratedArmorEffects", "SetBonusGenericDamage", "SetBonusMinionSlots", "SentrySlots", "ManaCostReduction", "ArmorPenetration"]:
        assert needle in item
    assert "GeneratedArmorItemTypes.ItemTypeFor(data)" in player
