from __future__ import annotations

from pathlib import Path

from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.capability_registry import INPUT_KINDS
from infini_local.core.runtime_authoring.terraria_vocabulary import (
    DAMAGE_CLASS_TOKENS,
    ITEM_USE_STYLE_TOKENS,
    VANILLA_AMMO_CATEGORY_TOKENS,
    DAMAGE_CLASS_TOKEN_PATTERN,
)

ROOT = Path(__file__).resolve().parents[2]


def test_author_vocabulary_is_finite_and_alias_free() -> None:
    assert INPUT_KINDS == ("primary_use", "alternate_use", "hold", "equipped")
    assert "passive" not in INPUT_KINDS
    assert "drink" not in ITEM_USE_STYLE_TOKENS
    assert "eat" not in ITEM_USE_STYLE_TOKENS
    assert "throwing" in DAMAGE_CLASS_TOKENS  # exact stable DamageClass.Throwing, not an alias
    assert "magic_summon_hybrid" in DAMAGE_CLASS_TOKENS
    assert "default" in DAMAGE_CLASS_TOKENS
    assert "rogue" not in DAMAGE_CLASS_TOKENS


def test_binding_use_policy_and_ammo_are_distinct_terraria_owners() -> None:
    ammo = CAPABILITY_REGISTRY["configure_vanilla_ammo_item"]
    assert "configure_consumption" not in CAPABILITY_REGISTRY
    assert tuple(ammo.params) == ("ammoCategory", "projectileId", "shootSpeedPxPerTick", "notAmmo")
    assert ammo.params["ammoCategory"].enum == VANILLA_AMMO_CATEGORY_TOKENS
    assert ammo.params["shootSpeedPxPerTick"].minimum == -20
    assert ammo.params["shootSpeedPxPerTick"].maximum == 80
    assert not ammo.requirements


def test_projectile_collision_exposes_terraria_liquid_and_immunity_semantics() -> None:
    collision = CAPABILITY_REGISTRY["set_projectile_collision"]
    assert tuple(collision.params) == (
        "tileCollide",
        "ignoreWater",
        "bounceCount",
        "pierce",
        "extraUpdates",
        "npcImmunityMode",
        "localNpcHitCooldownTicks",
    )
    assert collision.params["npcImmunityMode"].enum == ("owner", "local")
    assert collision.params["localNpcHitCooldownTicks"].minimum == -1


def test_lowery_is_generated_and_declares_custom_runtime_boundary() -> None:
    text = (ROOT / "lowery.md").read_text(encoding="utf-8")
    assert "Gameplay Author-visible semantic aliases: **нет**" in text
    assert "proxy-типы" in text
    assert "Item.ammo" in text and "Item.useAmmo" in text
    assert "ID-static immunity" in text
    assert "ModName/ClassName" in text


def test_healing_does_not_infer_potion_sickness() -> None:
    restore = CAPABILITY_REGISTRY["restore_resources_on_use"]
    assert tuple(restore.params) == ("healLife", "healMana", "potionSickness")
    apply = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs").read_text(encoding="utf-8")
    assert "item.potion = enabled && Gameplay.Potion;" in apply
    assert "item.potion = Gameplay.HealLife > 0" not in apply


def test_generated_parent_preserves_exact_ammo_and_potion_facts() -> None:
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm

    item = {
        "name": "Generated Ammo Tonic",
        "generatedData": {
            "gameplay": {
                "kind": "item",
                "damageClass": "throwing",
                "healLife": 25,
                "healMana": 0,
                "potion": False,
                "ammoCategory": "nail_friendly",
                "ammoProjectileId": 310,
                "ammoShootSpeedPxPerTick": 5.5,
                "notAmmo": True,
            },
            "runtimeProgram": {
                "apiVersion": "infini.runtime-program.v5",
                "schema": "infini.runtime-program.wire.v3",
                "itemEntityId": "item",
                "entities": [{"id": "item", "kind": "item_body"}],
                "bindings": [{
                    "id": "primary",
                    "input": "primary_use",
                    "role": "primary",
                    "usePolicy": {
                        "action": {"kind": "use_item_body", "targetId": "item"},
                        "stackCost": 1,
                        "contactDamage": False,
                    },
                }],
            },
        },
    }
    card = raw_parent_card_for_llm(item)
    gameplay = card["raw"]["generatedParent"]["gameplay"]
    assert gameplay["potion"] is False
    assert "primaryUseConsumeChancePercent" not in gameplay
    assert "alternateUseConsumeChancePercent" not in gameplay
    assert gameplay["ammoCategory"] == "nail_friendly"
    assert gameplay["ammoProjectileId"] == 310
    assert gameplay["ammoShootSpeedPxPerTick"] == 5.5
    assert gameplay["notAmmo"] is True
    bindings = card["raw"]["generatedParent"]["runtimeProgram"]["bindings"]
    assert bindings == [{
        "input": "primary_use",
        "usePolicy": {
            "action": {"kind": "use_item_body", "targetId": "item"},
            "stackCost": 1,
            "contactDamage": False,
        },
    }]


def test_cross_mod_identity_does_not_duplicate_placeable_runtime_facts() -> None:
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm

    card = raw_parent_card_for_llm({
        "name": "Glowing Mushroom",
        "internalName": "GlowingMushroom",
        "sourceMod": "Terraria",
        "fullName": "Terraria/GlowingMushroom",
        "createTile": 190,
        "createWall": -1,
        "consumable": True,
    })
    raw = card["raw"]
    assert raw["item"]["createTile"] == 190
    assert raw["vanillaFlags"]["createTile"] == 190
    assert "createTile" not in raw["crossModIdentity"]
    assert "createWall" not in raw["crossModIdentity"]
    assert "semantics" not in card


def test_exact_modded_damage_class_uses_tmodloader_full_name() -> None:
    import re

    assert re.fullmatch(DAMAGE_CLASS_TOKEN_PATTERN, "CalamityMod/RogueDamageClass")
    assert re.fullmatch(DAMAGE_CLASS_TOKEN_PATTERN, "throwing")
    assert re.fullmatch(DAMAGE_CLASS_TOKEN_PATTERN, "rogue") is None
    assert re.fullmatch(DAMAGE_CLASS_TOKEN_PATTERN, "CalamityMod:RogueDamageClass") is None
    vocabulary = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/TerrariaRuntimeVocabulary.cs").read_text(encoding="utf-8")
    assert "ModContent.TryFind<DamageClass>(exact" in vocabulary
    assert "Unknown exact damageClass" in vocabulary
    assert "?? DamageClass.Generic" not in vocabulary


def test_damage_class_parent_identity_is_single_exact_tmodloader_token() -> None:
    client = (ROOT / "ModSources/InfiniCrafterLocal/Common/Services/GeneratorClient.cs").read_text(encoding="utf-8")
    vocabulary = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/TerrariaRuntimeVocabulary.cs").read_text(encoding="utf-8")
    constants = (ROOT / "LocalGenerator/infini_local/pipelines/pipeline_runtime_constants.py").read_text(encoding="utf-8")
    cards = (ROOT / "LocalGenerator/infini_local/pipelines/parent_context_cards.py").read_text(encoding="utf-8")
    assert "CanonicalDamageClassToken" in vocabulary
    assert "=> TerrariaRuntimeVocabulary.CanonicalDamageClassToken" in client
    assert 'return damageClass is null ? (damage > 0 ? "generic" : "none") : "modded"' not in client
    assert "damageClassFullName" not in client
    assert "damageClassFullName" not in constants
    assert "damageClassFullName" not in cards


def test_loaded_content_ids_fail_closed_at_csharp_boundary() -> None:
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    dto = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs").read_text(encoding="utf-8")
    item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    for required in (
        "RarityLoader.RarityCount",
        "BuffLoader.BuffCount",
        "extra buff row cannot be null",
        "requires positive duration",
    ):
        assert required in normalize
    assert "TileLoader.TileCount" in dto
    assert "WallLoader.WallCount" in dto
    assert "BuffLoader.BuffCount" in dto
    assert "BuffId <= 0" in dto
    assert "buff.BuffCode > 0" in item


def test_exact_modded_damage_class_preserves_case_and_length() -> None:
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    dto = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs").read_text(encoding="utf-8")
    assert "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129);" in normalize
    assert "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129).ToLowerInvariant();" not in normalize
    assert "DamageClass = RuntimeText.Safe(DamageClass, 129);" in dto
    assert "DamageClass = RuntimeText.Safe(DamageClass, 129).ToLowerInvariant();" not in dto


def test_tool_and_value_units_match_exact_terraria_fields() -> None:
    item_stats = CAPABILITY_REGISTRY["configure_item_stats"]
    tool = CAPABILITY_REGISTRY["configure_tool"]
    assert "Item.value" in item_stats.params["valueCopper"].description
    assert "resale" in item_stats.params["valueCopper"].description
    assert tool.params["axePowerTooltipPercent"].maximum == 500
    assert tool.params["axePowerTooltipPercent"].multiple_of == 5
    assert "Item.axe" in tool.params["axePowerTooltipPercent"].description
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    assert "Gameplay.AxePower = ClampInt(Gameplay.AxePower, 0, 100);" in normalize
