from __future__ import annotations


import json


from copy import deepcopy


from pathlib import Path


import pytest


from infini_local.core import strict_json


from infini_local.core.errors import PlannerUnavailable


from infini_local.core.json_debug import bounded_json_dumps


from infini_local.pipelines.llm_authoring_pipeline import planner_runtime_promise_gate


from infini_local.pipelines import llm_authoring_pipeline as lap


from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack


from infini_local.pipelines.combine_validation import validate_and_repair


from infini_local.pipelines.item_power_knowledge import apply_item_knowledge, canonicalize


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _spear_parent() -> dict:
    return {
        "name": "Spear",
        "internalName": "Spear",
        "sourceMod": "Terraria",
        "damage": 8,
        "damageClass": "melee",
        "useStyle": 5,
        "useTime": 31,
        "useAnimation": 31,
        "rare": 1,
        "value": 1210,
        "maxStack": 1,
        "consumable": False,
        "material": False,
        "noMelee": True,
        "noUseGraphic": True,
        "shoot": 49,
        "shootSpeed": 3.7,
        "directProjectileRaw": {
            "source": "item.shoot",
            "type": 49,
            "internalName": "Spear",
            "sourceMod": "Terraria",
            "width": 21,
            "height": 21,
            "scale": 1.2,
            "penetrate": -1,
            "timeLeft": 3600,
            "tileCollide": False,
            "ownerHitCheck": True,
            "damageClass": "melee",
        },
    }


def _rope_parent() -> dict:
    return {
        "name": "Rope",
        "internalName": "Rope",
        "sourceMod": "Terraria",
        "damage": -1,
        "damageClass": "none",
        "useStyle": 1,
        "useTime": 8,
        "useAnimation": 14,
        "rare": 0,
        "value": 10,
        "maxStack": 9999,
        "consumable": True,
        "material": True,
        "createTile": 213,
        "shoot": 0,
        "shootSpeed": 0,
    }


def _attach(plan: dict, a: dict, b: dict, key: str) -> dict:
    ca = canonicalize(a)
    cb = canonicalize(b)
    data = validate_and_repair(plan, a, b, ca, cb, key)
    data = apply_item_knowledge(data, a, b, ca, cb)
    return attach_gameplay_and_attack(data, a, b, ca, cb)


def _contract_check_final_attack_materializes_compiler_affordances_for_held_thrust() -> None:
    plan = {
        "name": "Rope Spear",
        "concept": {
            "fantasy": "A compact rope-bound spear.",
            "mergeLogic": "Spear supplies the attack and rope supplies the grip.",
            "coreMechanic": "A held thrust keeps the short rope-bound spear visible.",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "callId": "item_stats",
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "melee",
                        "damage": 17,
                        "useTimeTicks": 28,
                        "maxStack": 1,
                    },
                },
                {
                    "callId": "primary_thrust",
                    "fn": "perform_melee_attack",
                    "params": {
                        "family": "spear",
                        "speed": 8,
                        "rangeTiles": 20,
                        "lifetimeTicks": 28,
                        "shotCount": 1,
                        "spreadRadians": 0,
                        "pierce": 1,
                        "projectileShape": "short rope-bound spear",
                    },
                },
            ],
        },
        "visual": {"itemPrompt": "Short iron spear with a rope-bound grip."},
    }
    data = _attach(plan, _spear_parent(), _rope_parent(), "test_final_affordances_rope_spear")

    assert data["attack"]["runtimeFamily"] == "thrust"
    assert data["attack"]["useStyleCode"] == 5
    assert data["attack"]["hideUseGraphic"] is True
    assert data["attack"]["disableItemMeleeHitbox"] is True
    assert data["attack"]["ownerHitCheck"] is True
    assert data["attack"]["channelUse"] is False
    assert data["gameplay"]["heldVisibility"] == "show_projectile"
    assert data["gameplay"]["releaseTiming"] == "instant"
    assert data["gameplay"]["handPose"] == "two_hand"


def _contract_check_returning_family_gets_pre_release_held_presentation() -> None:
    plan = {
        "name": "Rope Chakram",
        "concept": {
            "fantasy": "Returning rope blade",
            "mergeLogic": "The blade supplies the edge while rope forms the returning grip.",
            "coreMechanic": "The rope-bound blade returns after an early throw release.",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"callId": "item_stats", "fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 17, "useTimeTicks": 28, "maxStack": 1}},
                {"callId": "primary_returning", "fn": "perform_melee_attack", "params": {"family": "boomerang", "speed": 9, "rangeTiles": 24, "lifetimeTicks": 90, "shotCount": 1, "spreadRadians": 0, "pierce": 1, "projectileShape": "rope chakram"}},
            ],
        },
        "visual": {"itemPrompt": "Compact rope-bound chakram."},
    }
    data = _attach(plan, _spear_parent(), _rope_parent(), "test_returning_held_presentation")

    assert data["attack"]["runtimeFamily"] == "returning"
    assert data["gameplay"]["heldVisibility"] == "show_item"
    assert data["gameplay"]["releaseTiming"] == "early"
    assert data["gameplay"]["handPose"] == "throwing"


def _contract_check_csharp_projectile_owned_families_disable_vanilla_contact_damage() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs"
    ).read_text(encoding="utf-8")

    assert "bool projectileOwnedUse = GeneratedRuntimeFamilyPolicy.IsProjectileOwned(runtimeFamily);" in source
    assert "IsFreeProjectileFamily" not in source
    assert "item.noMelee = Attack.DisableItemMeleeHitbox || projectileOwnedUse;" in source
    assert "item.noUseGraphic = Attack.HideUseGraphic || projectileOwnedUse;" in source


def _contract_check_csharp_movement_executor_owns_special_projectile_rotation() -> None:
    root = Path(__file__).resolve().parents[2]
    runtime = (
        root / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs"
    ).read_text(encoding="utf-8")
    executors = (
        root / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs"
    ).read_text(encoding="utf-8")

    assert "movementOwnsRotation = RunMovementExecutor(movement);" in runtime
    assert "if (!beamLike && !chargeReleaseLike && !sentryLike && !overheadBarrage && !thrustLike && !movementOwnsRotation)" in runtime
    assert "bool OwnsRotation(ProjectileRuntimeContext context);" in executors
    assert "context.MovementCode is 5 or 14" in executors
    assert "p.Projectile.rotation +=" in executors


def _contract_check_remote_held_payload_sends_explicit_inactive_transition() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "ModSources/InfiniCrafterLocal/Common/Players/GeneratedHeldItemDrawLayer.cs"
    ).read_text(encoding="utf-8")

    assert "HeldItemPresentationSyncVersion = 4" in source
    assert "public bool ActiveUse;" in source
    assert "writer.Write(payload.ActiveUse);" in source
    assert "ActiveUse = reader.ReadBoolean()" in source
    assert "return remotePayload?.ActiveUse == true;" in source
    assert "bool wasActive = lastSyncKey.StartsWith(activeKeyPrefix" in source
    assert "if (!activeUse && !wasActive)" in source


def _contract_check_csharp_held_draw_consumes_visibility_and_release_contract() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "ModSources/InfiniCrafterLocal/Common/Players/GeneratedHeldItemDrawLayer.cs"
    ).read_text(encoding="utf-8")

    assert "public byte AnimationRemaining;" in source
    assert "writer.Write(payload.AnimationRemaining);" in source
    assert "AnimationRemaining = reader.ReadByte()" in source
    assert "private static bool ShouldDrawHeldSprite(" in source
    assert 'heldVisibility is "hide_item" or "show_projectile"' in source
    assert 'releaseTiming == "early"' in source
    assert "ShouldDrawHeldSprite(data, player, remotePayload)" in source


def _contract_check_generated_items_drive_composite_arm_pose_from_runtime_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    item_main = (
        root / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs"
    ).read_text(encoding="utf-8")
    item_pose_path = root / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.UseStyle.cs"
    runtime = (
        root / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs"
    ).read_text(encoding="utf-8")

    assert "public partial class GeneratedItem : ModItem" in item_main
    assert item_pose_path.exists()
    item_pose = item_pose_path.read_text(encoding="utf-8")
    assert "public override void UseStyle(Player player, Rectangle heldItemFrame)" in item_pose
    assert "player.SetCompositeArmFront" in item_pose
    assert "player.SetCompositeArmBack" in item_pose
    assert "ApplyOwnerArmPose(owner, dir, twoHanded: true);" in runtime
    assert "ApplyOwnerArmPose(owner, -toOwner, twoHanded: false);" in runtime
    assert "ApplyOwnerArmPose(owner, Projectile.Center - owner.MountedCenter, twoHanded: false);" in runtime
    assert "ApplyOwnerArmPose(owner, dir, twoHanded: false);" in runtime


def _contract_check_bounded_debug_json_is_parseable_finite_and_circular_safe() -> None:
    short = bounded_json_dumps(
        {"values": [float("nan"), float("inf"), float("-inf")]},
        max_chars=400,
    )
    assert strict_json.loads(short) == {"values": ["nan", "inf", "-inf"]}

    circular: dict[str, object] = {"huge": "x" * 4000}
    circular["self"] = circular
    bounded = bounded_json_dumps(circular, max_chars=180)
    parsed = strict_json.loads_object(bounded)
    assert len(bounded) <= 180
    assert parsed["truncated"] is True
    assert isinstance(parsed["preview"], str)


def _honest_author_item_bolt(name: str = "Honest Bolt") -> dict:
    return {
        "name": name,
        "category": "weapon",
        "concept": {
            "fantasy": "A fast bounded bolt.",
            "mergeLogic": "Both parents remain readable in the compact launcher and bolt body.",
            "coreMechanic": "One tap launches one fast finite straight-flying bolt.",
        },
        "runtimeContract": {
            "primaryVerb": "shoot",
            "controlStyle": "tap",
            "playerViewTimeline": [
                {"phase": "use", "description": "The player fires one bolt."},
                {"phase": "travel", "description": "The bolt travels straight until hit or expiry."},
            ],
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "runtimeStateIntent": "No persistent state.",
            "sourceReading": "Both source materials remain literal parts of the launcher and bolt.",
            "balanceIntent": "One finite projectile per tap.",
            "anomalyFlags": [],
            "sourceRolePreservation": {"itemA": "launcher body", "itemB": "bolt body"},
            "visualIntent": {
                "item": "A compact launcher made from both source parts.",
                "projectile": "One short straight bolt.",
                "impact": "A brief chip burst.",
                "vfxIntent": "A restrained launch streak and small impact chips.",
                "vfxAvoid": "No orbit, field, aura, or extra projectile.",
            },
            "engineCalls": [
                {"callId": "item_stats", "fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 10, "useTimeTicks": 20, "maxStack": 1}},
                {"callId": "primary_projectile", "fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 8, "rangeTiles": 30, "lifetimeTicks": 60, "shotCount": 1, "spreadRadians": 0, "pierce": 1, "projectileShape": "short bolt"}},
            ],
        },
    }


def _contract_check_try_llm_plan_keeps_one_call_for_honest_plan(monkeypatch) -> None:
    response = _honest_author_item_bolt()
    calls: list[dict] = []

    def fake_chat(req: dict, timeout: int) -> dict:
        calls.append(req)
        return {"choices": [{"message": {"content": json.dumps(response)}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(lap, "llm_chat_json", fake_chat)
    monkeypatch.setattr(lap, "trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(lap, "log_event", lambda *args, **kwargs: None)
    parent = {"name": "Wood", "internalName": "Wood", "sourceMod": "Terraria", "type": 9, "maxStack": 9999}

    result = lap.try_llm_plan(parent, parent, {}, {}, "promise_no_retry")

    assert result is not None
    assert len(calls) == 1


def _contract_check_try_llm_plan_does_not_runtime_reject_payload_above_test_budget(monkeypatch) -> None:
    response = _honest_author_item_bolt("Oversized Context Bolt")
    calls: list[dict] = []

    def fake_chat(req: dict, timeout: int) -> dict:
        calls.append(req)
        return {"choices": [{"message": {"content": json.dumps(response)}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "build_llm_author_payload", lambda *args, **kwargs: {"oversizedParentContext": "x" * 25_000})
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(lap, "llm_chat_json", fake_chat)
    monkeypatch.setattr(lap, "trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(lap, "log_event", lambda *args, **kwargs: None)
    parent = {"name": "Wood", "internalName": "Wood", "sourceMod": "Terraria", "type": 9, "maxStack": 9999}

    result = lap.try_llm_plan(parent, parent, {}, {}, "oversized_runtime_context")

    assert result is not None
    assert len(calls) == 1
    assert len(calls[0]["messages"][1]["content"]) > 24_750


def _contract_check_csharp_item_bodied_projectile_falls_back_to_item_sprite() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Visuals.cs"
    ).read_text(encoding="utf-8")

    assert "private bool UsesItemSpriteAsProjectileByDefault()" in source
    assert "registryData.Visual?.SpritePath" in source
    assert "UsesItemSpriteAsProjectileByDefault()" in source


def test_241_holistic_instability_bugfixes_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request)
