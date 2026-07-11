from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines.parent_context_pipeline import effective_projectile_profile_of
from infini_local.pipelines.parent_context_pipeline import projectile_profile_of
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


def _check_raw_parent_card_keeps_runtime_facts_but_not_texture_metrics_for_llm() -> None:
    bow = {
        "name": "Copper Bow",
        "internalName": "CopperBow",
        "sourceMod": "Terraria",
        "damage": 6,
        "damageClass": "ranged",
        "useTime": 25,
        "useAnimation": 25,
        "useStyle": 5,
        "useAmmo": 1,
        "shoot": 1,
        "shootSpeed": 6.6,
        "noMelee": True,
        "textureMetrics": {"textureWidth": 40, "textureHeight": 40, "visibleMajorAxis": 30},
        "directProjectileRaw": {
            "source": "item.shoot",
            "type": 1,
            "internalName": "WoodenArrowFriendly",
            "sourceMod": "Terraria",
            "aiStyle": 1,
            "penetrate": 1,
            "timeLeft": 1200,
            "extraUpdates": 0,
            "tileCollide": True,
            "light": 0.0,
            "arrow": True,
            "textureMetrics": {"textureWidth": 32, "visibleMajorAxis": 25},
            "setsRaw": {"trailCacheLength": 0, "trailingMode": 0},
        },
        "effectiveProjectileRaw": {
            "source": "weapon_item.shoot_field",
            "type": 1,
            "internalName": "WoodenArrowFriendly",
            "sourceMod": "Terraria",
            "aiStyle": 1,
            "penetrate": 1,
            "timeLeft": 1200,
            "extraUpdates": 0,
            "tileCollide": True,
            "light": 0.0,
            "arrow": True,
            "textureMetrics": {"textureWidth": 32, "visibleMajorAxis": 25},
        },
        "ammoRaw": {
            "mode": "weapon_uses_ammo",
            "ammoId": 1,
            "weaponShootFieldProjectileRaw": {"source": "weapon_item.shoot_field", "type": 1, "internalName": "WoodenArrowFriendly", "aiStyle": 1, "light": 0.0, "arrow": True},
            "fallbackAmmoRaw": [{"internalName": "WoodenArrow", "ammo": 1, "shoot": 1, "shootSpeed": 3.0}],
            "fallbackProjectileRaw": [{"source": "fallback_basic_ammo_scan.shoot", "type": 1, "internalName": "WoodenArrowFriendly", "aiStyle": 1, "light": 0.0, "arrow": True}],
        },
    }

    card = raw_parent_card_for_llm(bow)
    assert card["raw"]["item"]["shoot"] == 1
    assert card["raw"]["item"]["useAmmo"] == 1
    assert card["raw"]["directProjectile"]["source"] == "item.shoot"
    assert card["raw"]["effectiveProjectile"]["source"] == "weapon_item.shoot_field"
    assert card["raw"]["effectiveProjectile"].get("sameAs") == "raw.directProjectile"
    assert card["raw"]["ammo"]["mode"] == "weapon_uses_ammo"
    assert card["raw"]["ammo"].get("weaponShootFieldProjectileRaw", {}).get("internalName") == "WoodenArrowFriendly"
    assert "behaviorDigest" in card["raw"]["directProjectile"]
    digest = card["raw"]["directProjectile"]["behaviorDigest"]
    assert digest["mechanicalHint"] == "free_projectile_with_tile_collision"
    assert "vanillaAiStyleBucket" not in digest
    assert "aiStyleExamplesFromDump" not in digest
    assert "aiStyle" not in card["raw"]["directProjectile"]
    assert "fallbackProjectileRaw" not in card["raw"].get("ammo", {})

    blob = json.dumps(card, ensure_ascii=False).lower()
    assert blob.count("woodenarrowfriendly") <= 2
    assert "shuriken" not in blob
    assert "long-lived projectile/effect" not in blob
    assert "texturemetrics" not in blob
    assert "unknown" not in blob
    assert "not observed" not in blob
    assert "no magic" not in blob
    assert "materialeffects" not in blob
    assert "visualjustification" not in blob

    assert projectile_profile_of(bow)["source"] == "item.shoot"
    assert effective_projectile_profile_of(bow)["source"] == "weapon_item.shoot_field"


def _check_raw_parent_card_includes_generated_parent_summary() -> None:
    item = {
        "name": "Void-Mana Flail",
        "internalName": "GeneratedItem",
        "sourceMod": "InfiniCrafterLocal",
        "generatedData": {
            "GeneratedParentSummary": {
                "name": "Void-Mana Flail",
                "fantasy": "A heavy mana flail with a void anchor.",
                "category": "weapon",
                "damageClass": "magic",
                "runtime": "flail",
                "visualIdentity": "purple chain sphere with mana glow",
                "notableEffects": ["void pull", "generated buff: light"],
            },
            "gameplay": {"kind": "weapon", "damageClass": "magic", "damage": 42},
            "attack": {"enabled": True, "runtimePlanAuthored": True, "runtimeFamily": "flail", "movement": "flail_tether", "effect": "shadow", "onHit": "blackhole_pull"},
        },
    }
    card = raw_parent_card_for_llm(item)
    summary = card["raw"]["generatedParent"]["summary"]
    assert summary["fantasy"] == "A heavy mana flail with a void anchor."
    assert summary["runtime"] == "flail"
    assert "void pull" in summary["notableEffects"]


def _check_raw_parent_card_includes_cross_mod_identity_facts() -> None:
    item = {
        "name": "Example Mod Wand",
        "internalName": "ExampleWand",
        "sourceMod": "ExampleMod",
        "fullName": "ExampleMod/ExampleWand",
        "damageClassFullName": "Terraria/Magic",
        "shootProjectileFullName": "ExampleMod/ExampleBolt",
        "createTile": -1,
        "createWall": -1,
    }
    card = raw_parent_card_for_llm(item)
    x = card["raw"]["crossModIdentity"]
    assert x["sourceMod"] == "ExampleMod"
    assert x["fullName"] == "ExampleMod/ExampleWand"
    assert x["damageClassFullName"] == "Terraria/Magic"
    assert x["shootProjectileFullName"] == "ExampleMod/ExampleBolt"


def _check_raw_parent_card_includes_compact_vanilla_flags_v3() -> None:
    item = {
        "name": "Suspicious Amber Charm",
        "internalName": "SuspiciousAmberCharm",
        "sourceMod": "Terraria",
        "consumable": False,
        "material": True,
        "accessory": True,
        "expert": True,
        "shoot": 0,
        "useAmmo": 0,
        "createTile": -1,
        "createWall": -1,
    }
    card = raw_parent_card_for_llm(item)
    flags = card["raw"]["vanillaFlags"]
    assert flags["material"] is True
    assert flags["accessory"] is True
    assert flags["expert"] is True
    assert "bait" not in flags
    assert flags["createTile"] == -1
    assert "consumable" not in flags


def _check_raw_parent_card_marks_fishing_bait_as_future_disabled_context() -> None:
    item = {
        "name": "Fiberglass Fishing Pole",
        "internalName": "FiberglassFishingPole",
        "sourceMod": "Terraria",
        "fishingPole": 27,
        "bait": 0,
        "shoot": 0,
        "useAmmo": 0,
        "createTile": -1,
        "createWall": -1,
    }
    card = raw_parent_card_for_llm(item)
    assert card["raw"]["item"]["fishingPole"] == 27
    assert card["raw"]["vanillaFlags"]["fishingPole"] == 27
    fishing = card["semantics"]["fishingBaitSemantics"]
    assert fishing["supportStatus"] == "future_disabled_for_generated_outputs"
    assert "fishing_pole_parent" in fishing["roles"]
    assert "does not generate executable fishing poles or bait items" in fishing["note"]

    bait = {
        "name": "Master Bait",
        "internalName": "MasterBait",
        "sourceMod": "Terraria",
        "fishingPole": 0,
        "bait": 50,
        "shoot": 0,
        "useAmmo": 0,
        "createTile": -1,
        "createWall": -1,
    }
    bait_card = raw_parent_card_for_llm(bait)
    assert bait_card["raw"]["item"]["bait"] == 50
    assert bait_card["raw"]["vanillaFlags"]["bait"] == 50
    assert "bait_parent" in bait_card["semantics"]["fishingBaitSemantics"]["roles"]

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_raw_parent_card_keeps_runtime_facts_but_not_texture_metrics_for_llm',
    '_check_raw_parent_card_includes_generated_parent_summary',
    '_check_raw_parent_card_includes_cross_mod_identity_facts',
    '_check_raw_parent_card_includes_compact_vanilla_flags_v3',
    '_check_raw_parent_card_marks_fishing_bait_as_future_disabled_context'
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


def test_parent_card_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
