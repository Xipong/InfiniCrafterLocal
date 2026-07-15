from __future__ import annotations

import json
from pathlib import Path

import pytest

from infini_local.core import strict_json
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.runtime_contracts import validate_runtime_contract
from infini_local.core.runtime_promise_truth import validate_runtime_promises
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
        "tooltip": "A compact rope-bound spear.",
        "concept": {
            "fantasy": "A compact rope-bound spear.",
            "mergeLogic": "Spear supplies the attack and rope supplies the grip.",
            "weirdTwist": "The rope flutters on thrust.",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
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
        "tooltip": "A returning rope-bound blade.",
        "concept": {"fantasy": "Returning rope blade", "mergeLogic": "blade plus rope", "weirdTwist": "returns"},
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 17, "useTimeTicks": 28, "maxStack": 1}},
                {"fn": "perform_melee_attack", "params": {"family": "boomerang", "speed": 9, "rangeTiles": 24, "lifetimeTicks": 90, "shotCount": 1, "spreadRadians": 0, "pierce": 1, "projectileShape": "rope chakram"}},
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


def _contract_check_promise_truth_ignores_descriptive_material_words_but_keeps_mechanical_controls() -> None:
    decorative = {
        "tooltip": (
            "A burnished twin-edged platform-steel blade with a charged crystal, "
            "feline engraving, and heat-forged guard."
        ),
    }
    decorative_report = validate_runtime_promises(decorative, {})
    assert decorative_report["claims"] == []
    assert decorative_report["unsupportedPromises"] == []

    mechanical = {
        "tooltip": (
            "The projectile bounces off walls, burns enemies on hit, and creates "
            "a temporary platform the player can stand on."
        ),
    }
    mechanical_report = validate_runtime_promises(mechanical, {"movement": "straight"})
    kinds = {claim["kind"] for claim in mechanical_report["claims"]}
    assert {"projectile_bounce", "burn_on_hit", "temporary_platform"} <= kinds


def _contract_check_promise_truth_rerun_removes_only_its_stale_markers() -> None:
    data = {
        "tooltip": "The projectile bounces off walls.",
        "unsupportedPromises": ["external:manual_review"],
    }
    first = validate_runtime_promises(data, {"movement": "straight"})
    assert "unsupported:projectile_bounce" in first["unsupportedPromises"]
    assert set(data["unsupportedPromises"]) == {
        "external:manual_review",
        "unsupported:projectile_bounce",
    }

    data["tooltip"] = "A polished steel bolt with a blue ribbon."
    second = validate_runtime_promises(data, {"movement": "straight"})
    assert second["unsupportedPromises"] == []
    assert data["unsupportedPromises"] == ["external:manual_review"]


def _contract_check_partial_promise_cannot_retain_stale_executable_status() -> None:
    claim = "Charges the weapon's power before releasing the stored shot."
    data = {
        "tooltip": claim,
        "runtimePlan": {"engineCalls": [{"fn": "state_meter", "params": {"stateKey": "charge"}}]},
        "runtimeContract": {
            "executionStatus": "executable",
            "mechanicClaims": [{"claim": claim, "status": "executable", "backing": "state_meter"}],
        },
    }
    report = validate_runtime_promises(data, {})
    charge_claims = [entry for entry in report["claims"] if entry["kind"] == "charge_release"]
    assert charge_claims
    assert all(entry["status"] == "partial" for entry in charge_claims)
    assert data["runtimeContract"]["executionStatus"] == "partial"


def _contract_check_runtime_contract_maps_live_supported_statuses_and_engine_call_backing() -> None:
    data = {
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "returning"}},
            ]
        },
        "runtimeContract": {
            "executionStatus": "stable",
            "mechanicClaims": [
                {
                    "claim": "throws the weapon",
                    "backing": "shoot_projectile",
                    "backingRefs": [{"source": "engineCall", "callIndex": 1, "fn": "shoot_projectile", "field": "runtimeFamily", "expected": "returning"}],
                    "status": "supported",
                },
                {
                    "claim": "returns to the wielder",
                    "backing": "AttackSpec returning executor",
                    "backingRefs": [{"source": "compiledAttack", "field": "runtimeFamily", "expected": "returning"}],
                    "status": "active",
                },
            ],
        },
    }

    report = validate_runtime_contract(data, {"runtimeFamily": "returning"})

    assert report["unsupportedPromises"] == []
    assert report["executionStatus"] == "executable"
    assert [claim["status"] for claim in data["runtimeContract"]["mechanicClaims"]] == ["executable", "executable"]


def _contract_check_runtime_contract_does_not_trust_supported_label_without_backing() -> None:
    data = {
        "runtimePlan": {"engineCalls": [{"fn": "set_item_stats", "params": {}}]},
        "runtimeContract": {
            "executionStatus": "stable",
            "mechanicClaims": [
                {"claim": "summons orbiting blades", "backing": "", "status": "supported"},
            ],
        },
    }

    report = validate_runtime_contract(data, {})

    assert report["executionStatus"] == "partial"
    assert data["runtimeContract"]["mechanicClaims"][0]["status"] == "partial"


def _contract_check_runtime_promise_truth_detects_orbiting_and_homing_without_executors() -> None:
    data = {
        "tooltip": "Summons three orbiting blades that seek enemies.",
        "concept": {"fantasy": "Three blades orbit the wielder and home into targets."},
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "summon_behavior", "params": {"family": "minion"}},
            ],
        },
    }

    report = validate_runtime_promises(data, {"runtimeFamily": "summon", "movement": "straight"})

    assert "unsupported:orbiting_companion" in report["unsupportedPromises"]
    assert "unsupported:projectile_homing" in report["unsupportedPromises"]


def _contract_check_planner_promise_gate_blocks_gameplay_prose_but_allows_executable_homing() -> None:
    bad = {
        "tooltip": "Summons orbiting blades that seek enemies.",
        "runtimePlan": {"engineCalls": [{"fn": "summon_behavior", "params": {"family": "minion"}}]},
    }
    good = {
        "tooltip": "Shots home into targets.",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "movement": "homing"}},
            ]
        },
    }

    bad_gate = planner_runtime_promise_gate(bad)
    good_gate = planner_runtime_promise_gate(good)

    assert bad_gate["ok"] is False
    assert {entry["kind"] for entry in bad_gate["blockingClaims"]} >= {"orbiting_companion", "projectile_homing"}
    assert good_gate["ok"] is True


def _contract_check_planner_promise_gate_does_not_treat_material_heat_as_heat_jam() -> None:
    plan = {
        "name": "Heat-Forged Bolt",
        "tooltip": "A heat-forged bolt with a polished steel tip.",
        "runtimeContract": {
            "schema": "infini.runtime-contract.v2",
            "primaryVerb": "shoot a straight bolt",
            "controlStyle": "tap",
            "mechanicClaims": [
                {
                    "claim": "A heat-forged bolt with a polished steel tip.",
                    "backing": "visual_only: material description",
                    "status": "visual_only",
                },
                {
                    "claim": "shoots a straight bolt",
                    "backing": "shoot_projectile",
                    "backingRefs": [{
                        "source": "engineCall",
                        "callIndex": 1,
                        "fn": "shoot_projectile",
                        "field": "runtimeFamily",
                        "expected": "shoot",
                    }],
                    "status": "executable",
                },
            ],
            "playerViewTimeline": ["held", "fired", "travels", "hits", "expires"],
            "executionStatus": "executable",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 10, "useTimeTicks": 20, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "movement": "straight", "speed": 8, "lifetimeTicks": 60, "projectileShape": "bolt"}},
            ],
        },
    }

    gate = planner_runtime_promise_gate(plan)

    assert gate["ok"] is True
    assert all(claim["kind"] != "heat_jam" for claim in gate["blockingClaims"])

    mechanical_gate = planner_runtime_promise_gate({
        **plan,
        "tooltip": "Builds heat while firing and must vent before the next burst.",
    })
    assert mechanical_gate["ok"] is False
    assert any(claim["kind"] == "heat_jam" for claim in mechanical_gate["blockingClaims"])


def _contract_check_try_llm_plan_reauthors_once_after_blocking_promise(monkeypatch) -> None:
    responses = [
        {
            "name": "False Orbit",
            "tooltip": "Summons orbiting blades that seek enemies.",
            "runtimePlan": {"resultKind": "weapon", "engineCalls": [{"fn": "summon_behavior", "params": {"family": "minion"}}]},
        },
        {
            "name": "Honest Bolt",
            "tooltip": "Shoots a fast bolt.",
            "runtimeContract": {
                "schema": "infini.runtime-contract.v2",
                "primaryVerb": "shoot a fast bolt",
                "controlStyle": "tap",
                "mechanicClaims": [{"claim": "shoots a fast bolt", "backing": "shoot_projectile", "backingRefs": [{"source": "engineCall", "callIndex": 1, "fn": "shoot_projectile", "field": "runtimeFamily", "expected": "shoot"}], "status": "executable"}],
                "playerViewTimeline": ["item held", "bolt emitted", "wall collision ends bolt", "NPC collision damages", "bolt expires"],
                "executionStatus": "executable",
            },
            "runtimePlan": {
                "resultKind": "weapon",
                "engineCalls": [
                    {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 10, "useTimeTicks": 20, "maxStack": 1}},
                    {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "movement": "straight", "speed": 8, "lifetimeTicks": 60, "projectileShape": "bolt"}},
                ],
            },
        },
    ]
    calls: list[dict] = []

    def fake_chat(req: dict, timeout: int) -> dict:
        calls.append(req)
        return {"choices": [{"message": {"content": json.dumps(responses[len(calls) - 1])}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(lap, "llm_chat_json", fake_chat)
    monkeypatch.setattr(lap, "trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(lap, "log_event", lambda *args, **kwargs: None)
    parent = {"name": "Wood", "internalName": "Wood", "sourceMod": "Terraria", "type": 9, "maxStack": 9999}

    result = lap.try_llm_plan(parent, parent, {}, {}, "promise_retry")

    assert result is not None
    assert result["name"] == "Honest Bolt"
    assert len(calls) == 2
    assert result["debug"]["plannerPromiseGate"]["ok"] is True
    retry_packet = json.loads(calls[1]["messages"][-1]["content"])
    backing_rules = retry_packet["backingRefRules"]
    assert any("source must be exactly" in rule and "engineCall" in rule for rule in backing_rules)
    assert any("zero-based absolute index into runtimePlan.engineCalls" in rule for rule in backing_rules)
    assert any('"source":"engineCall"' in rule and '"callIndex":1' in rule for rule in backing_rules)


def _contract_check_try_llm_plan_reauthors_again_when_first_feedback_creates_a_new_blocking_promise(monkeypatch) -> None:
    responses = [
        {
            "name": "False Orbit",
            "tooltip": "Summons orbiting blades.",
            "runtimePlan": {"resultKind": "weapon", "engineCalls": [{"fn": "summon_behavior", "params": {"family": "minion"}}]},
        },
        {
            "name": "False Orbit Again",
            "tooltip": "Keeps orbiting blades around the player.",
            "runtimePlan": {"resultKind": "weapon", "engineCalls": [{"fn": "summon_behavior", "params": {"family": "minion"}}]},
        },
        {
            "name": "Honest Bolt",
            "tooltip": "Shoots a fast bolt.",
            "runtimeContract": {
                "schema": "infini.runtime-contract.v2",
                "primaryVerb": "shoot a fast bolt",
                "controlStyle": "tap",
                "mechanicClaims": [{"claim": "shoots a fast bolt", "backing": "shoot_projectile", "backingRefs": [{"source": "engineCall", "callIndex": 1, "fn": "shoot_projectile", "field": "runtimeFamily", "expected": "shoot"}], "status": "executable"}],
                "playerViewTimeline": ["item held", "bolt emitted", "wall collision ends bolt", "NPC collision damages", "bolt expires"],
                "executionStatus": "executable",
            },
            "runtimePlan": {
                "resultKind": "weapon",
                "engineCalls": [
                    {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 10, "useTimeTicks": 20, "maxStack": 1}},
                    {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "movement": "straight", "speed": 8, "lifetimeTicks": 60, "projectileShape": "bolt"}},
                ],
            },
        },
    ]
    calls: list[dict] = []

    def fake_chat(req: dict, timeout: int) -> dict:
        calls.append(req)
        return {"choices": [{"message": {"content": json.dumps(responses[len(calls) - 1])}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(lap, "llm_chat_json", fake_chat)
    monkeypatch.setattr(lap, "trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(lap, "log_event", lambda *args, **kwargs: None)
    parent = {"name": "Wood", "internalName": "Wood", "sourceMod": "Terraria", "type": 9, "maxStack": 9999}

    result = lap.try_llm_plan(parent, parent, {}, {}, "promise_retry_twice")

    assert result is not None
    assert result["name"] == "Honest Bolt"
    assert len(calls) == 3
    assert result["debug"]["plannerPromiseGate"]["ok"] is True


def _contract_check_try_llm_plan_preserves_explicit_promise_exhaustion_reason(monkeypatch) -> None:
    blocked = {
        "name": "False Orbit",
        "tooltip": "Summons orbiting blades.",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [{"fn": "summon_behavior", "params": {"family": "minion"}}],
        },
    }
    calls: list[dict] = []

    def fake_chat(req: dict, timeout: int) -> dict:
        calls.append(req)
        return {"choices": [{"message": {"content": json.dumps(blocked)}}]}

    monkeypatch.setattr(lap, "USE_LLM", True)
    monkeypatch.setattr(lap, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(lap, "llm_chat_json", fake_chat)
    monkeypatch.setattr(lap, "trace_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(lap, "log_event", lambda *args, **kwargs: None)
    parent = {"name": "Wood", "internalName": "Wood", "sourceMod": "Terraria", "type": 9, "maxStack": 9999}

    with pytest.raises(PlannerUnavailable, match="repeated unsupported gameplay promises"):
        lap.try_llm_plan(parent, parent, {}, {}, "promise_retry_exhausted")

    assert len(calls) == 3



def _contract_check_try_llm_plan_keeps_one_call_for_honest_plan(monkeypatch) -> None:
    response = {
        "name": "Honest Bolt",
        "tooltip": "Shoots a fast bolt.",
        "runtimeContract": {
            "schema": "infini.runtime-contract.v2",
            "primaryVerb": "shoot a fast bolt",
            "controlStyle": "tap",
            "mechanicClaims": [{"claim": "shoots a fast bolt", "backing": "shoot_projectile", "backingRefs": [{"source": "engineCall", "callIndex": 1, "fn": "shoot_projectile", "field": "runtimeFamily", "expected": "shoot"}], "status": "executable"}],
            "playerViewTimeline": ["item held", "bolt emitted", "wall collision ends bolt", "NPC collision damages", "bolt expires"],
            "executionStatus": "executable",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 10, "useTimeTicks": 20, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "movement": "straight", "speed": 8, "lifetimeTicks": 60, "projectileShape": "bolt"}},
            ],
        },
    }
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
    response = {
        "name": "Oversized Context Bolt",
        "tooltip": "Shoots a fast bolt.",
        "runtimeContract": {
            "schema": "infini.runtime-contract.v2",
            "primaryVerb": "shoot a fast bolt",
            "controlStyle": "tap",
            "mechanicClaims": [{
                "claim": "shoots a fast bolt",
                "backing": "shoot_projectile",
                "backingRefs": [{
                    "source": "engineCall",
                    "callIndex": 1,
                    "fn": "shoot_projectile",
                    "field": "runtimeFamily",
                    "expected": "shoot",
                }],
                "status": "executable",
            }],
            "playerViewTimeline": ["item held", "bolt emitted", "wall collision ends bolt", "NPC collision damages", "bolt expires"],
            "executionStatus": "executable",
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 10, "useTimeTicks": 20, "maxStack": 1}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "movement": "straight", "speed": 8, "lifetimeTicks": 60, "projectileShape": "bolt"}},
            ],
        },
    }
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


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_241_holistic_instability_bugfixes_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_final_attack_materializes_compiler_affordances_for_held_thrust',
            '_contract_check_returning_family_gets_pre_release_held_presentation',
            '_contract_check_csharp_projectile_owned_families_disable_vanilla_contact_damage',
            '_contract_check_csharp_movement_executor_owns_special_projectile_rotation',
            '_contract_check_remote_held_payload_sends_explicit_inactive_transition',
            '_contract_check_csharp_held_draw_consumes_visibility_and_release_contract',
            '_contract_check_generated_items_drive_composite_arm_pose_from_runtime_contract',
            '_contract_check_bounded_debug_json_is_parseable_finite_and_circular_safe',
            '_contract_check_promise_truth_ignores_descriptive_material_words_but_keeps_mechanical_controls',
            '_contract_check_promise_truth_rerun_removes_only_its_stale_markers',
            '_contract_check_partial_promise_cannot_retain_stale_executable_status',
            '_contract_check_runtime_contract_maps_live_supported_statuses_and_engine_call_backing',
            '_contract_check_runtime_contract_does_not_trust_supported_label_without_backing',
            '_contract_check_runtime_promise_truth_detects_orbiting_and_homing_without_executors',
            '_contract_check_planner_promise_gate_blocks_gameplay_prose_but_allows_executable_homing',
            '_contract_check_planner_promise_gate_does_not_treat_material_heat_as_heat_jam',
            '_contract_check_try_llm_plan_reauthors_once_after_blocking_promise',
            '_contract_check_try_llm_plan_reauthors_again_when_first_feedback_creates_a_new_blocking_promise',
            '_contract_check_try_llm_plan_preserves_explicit_promise_exhaustion_reason',
            '_contract_check_try_llm_plan_keeps_one_call_for_honest_plan',
            '_contract_check_try_llm_plan_does_not_runtime_reject_payload_above_test_budget',
            '_contract_check_csharp_item_bodied_projectile_falls_back_to_item_sprite',
        ),
    )
