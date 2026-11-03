from __future__ import annotations

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.capability_registry import INPUT_KINDS
from infini_local.core.runtime_authoring.terraria_vocabulary import (
    DAMAGE_CLASS_TOKENS,
    ITEM_USE_STYLE_TOKENS,
    VANILLA_AMMO_CATEGORY_TOKENS,
    DAMAGE_CLASS_TOKEN_PATTERN,
)


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
    ammo = CAPABILITY_REGISTRY["ammo_item"]
    assert "configure_consumption" not in CAPABILITY_REGISTRY
    assert tuple(ammo.params) == ("ammoCategory", "projectileId", "speedBonus", "notAmmo")
    assert ammo.params["ammoCategory"].enum == VANILLA_AMMO_CATEGORY_TOKENS
    assert ammo.params["speedBonus"].wire_schema()["minimum"] == -20
    assert ammo.params["speedBonus"].wire_schema()["maximum"] == 80
    assert not ammo.requirements


def test_projectile_collision_exposes_terraria_liquid_and_immunity_semantics() -> None:
    collision = CAPABILITY_REGISTRY["projectile_collision"]
    assert tuple(collision.params) == (
        "tileCollide",
        "ignoreWater",
        "bounceCount",
        "bounceSpeedRetention",
        "pierce",
        "updatesPerTick",
        "immunity",
    )
    assert (collision.params["updatesPerTick"].minimum, collision.params["updatesPerTick"].maximum) == (1, 6)
    variants = collision.params["immunity"].alternatives
    assert [spec.enum for spec in variants[:2]] == [("owner_shared",), ("once_per_npc",)]
    cooldown = variants[2].properties["localCooldown"]
    assert (cooldown.minimum, cooldown.maximum) == (0, 600)


def test_generated_parent_preserves_exact_ammo_and_potion_facts() -> None:
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm

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
    assert bindings == item["generatedData"]["runtimeProgram"]["bindings"]


def test_cross_mod_identity_does_not_duplicate_placeable_runtime_facts() -> None:
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm

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


def test_tool_and_value_units_match_exact_terraria_fields() -> None:
    item_stats = CAPABILITY_REGISTRY["item_stats"]
    tool = CAPABILITY_REGISTRY["tool_stats"]
    assert item_stats.params["valueCopper"].to_wire(12_345) == 12_345
    assert tool.params["axePower"].maximum == 500
    assert tool.params["axePower"].multiple_of == 5
    assert tool.params["axePower"].to_wire(45) == 9


def test_held_sprite_visibility_has_one_literal_native_authority() -> None:
    params = CAPABILITY_REGISTRY["item_use"].params
    assert "customHeldSprite" not in params
    assert "heldAlignment" not in params
    visibility = params["hideUseGraphic"]
    assert visibility.required
    assert visibility.to_wire(True) is True
    assert visibility.to_wire(False) is False
