from __future__ import annotations

from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
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


def test_damage_class_prompt_explains_choices_without_engine_documentation() -> None:
    from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload

    payload = build_llm_author_payload({}, {}, {}, {}, "class_guide")
    guide = payload["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["damageClass"]
    meanings = guide["meaningByToken"]
    assert set(meanings) == set(DAMAGE_CLASS_TOKENS)
    assert "does not receive generic bonuses" in meanings["default"]
    assert "all-class bonuses" in meanings["generic"]
    assert "attack speed has no effect" in meanings["melee_no_speed"]
    assert "melee attack speed" in meanings["summon_melee_speed"]
    assert all(token in meanings["magic_summon_hybrid"] for token in ("magic", "summon", "generic"))
    assert "not melee damage" in meanings["summon_melee_speed"]
    for token in ("summon", "summon_melee_speed"):
        assert "no standard critical-hit calculation" in meanings[token]
    assert "not used by vanilla items" in meanings["throwing"]
    assert "no movement" in guide["scope"]


def test_binding_use_policy_and_ammo_are_distinct_terraria_owners() -> None:
    ammo = CAPABILITY_REGISTRY["configure_vanilla_ammo_item"]
    assert "configure_consumption" not in CAPABILITY_REGISTRY
    assert tuple(ammo.params) == ("ammoCategory", "projectileId", "shootSpeedContributionPxPerUpdate", "notAmmo")
    assert ammo.params["ammoCategory"].enum == VANILLA_AMMO_CATEGORY_TOKENS
    assert ammo.params["shootSpeedContributionPxPerUpdate"].minimum == -20
    assert ammo.params["shootSpeedContributionPxPerUpdate"].maximum == 80
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
        "localNpcHitCooldownEngineUnits",
    )
    assert collision.params["npcImmunityMode"].enum == ("owner", "local")
    assert collision.params["localNpcHitCooldownEngineUnits"].minimum == -1


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
    assert bindings == item["generatedData"]["runtimeProgram"]["bindings"]


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


def test_tool_and_value_units_match_exact_terraria_fields() -> None:
    item_stats = CAPABILITY_REGISTRY["configure_item_stats"]
    tool = CAPABILITY_REGISTRY["configure_tool"]
    assert "Item.value" in item_stats.params["valueCopper"].description
    assert "resale" in item_stats.params["valueCopper"].description
    assert tool.params["axePowerTooltipPercent"].maximum == 500
    assert tool.params["axePowerTooltipPercent"].multiple_of == 5
    assert "Item.axe" in tool.params["axePowerTooltipPercent"].description


def test_held_sprite_visibility_is_only_presentation_metadata() -> None:
    release = CAPABILITY_REGISTRY["configure_item_use"].params["customHeldSprite"]
    assert release.enum == ("hidden", "visible", "inherit")
    assert dict(release.wire_enum) == {"hidden": "immediate", "visible": "on_release", "inherit": ""}
    assert "Custom held-root visibility only" in release.description
    assert "not gameplay release timing" in release.description
    assert "declared-size presentations" in release.description
    assert "historical keep behavior" in release.description
