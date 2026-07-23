from __future__ import annotations

from copy import deepcopy
from email.message import Message
from typing import Any
from urllib.error import HTTPError

from infini_local.core.boundary_models import canonical_visual_kit_view, runtime_plan_boundary_report
from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report
from infini_local.core.runtime_authoring.vocabulary import DELIVERIES
from infini_local.core.balance_report import build_balance_report
from infini_local.core.runtime_tooltip import compiled_runtime_tooltip
from infini_local.core.vfx_diversity import vfx_batch_diversity_report
from infini_local.core.vfx_manifest import attach_hybrid_vfx_manifest
from infini_local.core.vfx_composition_primitives import _vfx_event_stage
from infini_local.pipelines.runtime_presentation_policy import runtime_presentation_defaults
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.storage.world_storage import build_recipe_health


def _call(call_id: str, fn: str, **params: object) -> dict[str, Any]:
    return {"callId": call_id, "fn": fn, "params": params}


def _base_plan(result_kind: str, *calls: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": result_kind,
        "concept": {"coreMechanic": "untrusted free prose promise"},
        "runtimePlan": {
            "resultKind": result_kind,
            "engineCalls": list(calls),
            "sourceRolePreservation": {"itemA": "body", "itemB": "effect"},
            "runtimeStateIntent": "",
            "visualIntent": {"item": "", "projectile": "", "impact": "", "vfxIntent": "", "vfxAvoid": ""},
            "sourceReading": "",
            "balanceIntent": "",
            "anomalyFlags": [],
        },
    }


def test_shoot_swing_is_one_root_with_body_and_projectile_lanes() -> None:
    data = _base_plan(
        "tool",
        _call("stats", "set_item_stats", resultKind="tool", damageClass="melee", damage=38, useTimeTicks=20, useAnimationTicks=20, maxStack=1, craftYield=1, consumable=False),
        _call("tool", "tool_capability", pickPower=110, miningSpeedScale=1.0),
        _call("root", "shoot_projectile", runtimeFamily="shoot", delivery="swing", movement="straight", speed=9, rangeTiles=35, lifetimeTicks=90, shotCount=1, spreadRadians=0, pierce=1, extraUpdates=0, homingStrength=0),
    )
    report = runtime_plan_validation_report(deepcopy(data))
    assert report["ok"] is True, report
    patch = compile_runtime_plan_to_genome_patch(deepcopy(data))
    assert patch["runtimeFamily"] == "shoot"
    assert patch["delivery"] == "swing"
    assert patch["useStyleCode"] == 1
    assert patch["disableItemMeleeHitbox"] is False
    assert patch["hideUseGraphic"] is False
    presentation = runtime_presentation_defaults("shoot", "melee", "swing")
    assert presentation["handPose"] == "short_weapon"
    assert presentation["useStyle"] == 1


def test_projectile_only_and_invalid_family_delivery_are_distinct() -> None:
    projectile = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="ranged", damage=24, useTimeTicks=18, useAnimationTicks=18, maxStack=1, craftYield=1, consumable=False),
        _call("root", "shoot_projectile", runtimeFamily="shoot", delivery="shoot", movement="straight", speed=12, rangeTiles=50, lifetimeTicks=100, shotCount=1, spreadRadians=0, pierce=1, extraUpdates=0, homingStrength=0),
    )
    patch = compile_runtime_plan_to_genome_patch(deepcopy(projectile))
    assert patch["useStyleCode"] == 5
    assert patch["disableItemMeleeHitbox"] is True

    invalid = deepcopy(projectile)
    invalid["runtimePlan"]["engineCalls"][1]["params"].update({"runtimeFamily": "beam", "delivery": "swing", "movement": "phase"})
    report = runtime_plan_validation_report(invalid)
    assert report["ok"] is False
    assert any("runtimeFamily=beam rejects delivery=swing" in error for error in report["errors"])
    root_details = [detail for detail in report["errorDetails"] if detail.get("callId") == "root"]
    assert root_details
    assert {
        field
        for detail in root_details
        for field in detail.get("repairParamNames", [])
    } == {"runtimeFamily", "delivery"}
    assert "spear" not in DELIVERIES


def test_apply_player_effect_on_use_requires_an_executable_effect() -> None:
    item = _base_plan(
        "weapon",
        _call(
            "stats", "set_item_stats", resultKind="weapon", damageClass="magic",
            damage=20, useTimeTicks=30, useAnimationTicks=30,
            maxStack=1, craftYield=1, consumable=False,
        ),
        _call(
            "root", "shoot_projectile", runtimeFamily="cast", delivery="cast",
            movement="straight", speed=10, rangeTiles=40, lifetimeTicks=90,
            shotCount=1, spreadRadians=0, pierce=1,
        ),
        _call(
            "utility", "apply_player_effect_on_use", healLife=0, healMana=0,
            note="Recall player home after delay",
        ),
    )
    report = runtime_plan_validation_report(item)
    assert report["ok"] is False
    assert "apply_player_effect_on_use requires at least one executable heal, buff, or generatedBuff effect" in report["errors"]

    item["runtimePlan"]["engineCalls"][2]["params"]["healLife"] = 20
    assert runtime_plan_validation_report(item)["ok"] is True

    item["runtimePlan"]["engineCalls"].append(
        _call("alt", "set_alt_use_mode", mode="none", cooldownTicks=10)
    )
    alt_report = runtime_plan_validation_report(item)
    assert alt_report["ok"] is False
    assert "set_alt_use_mode requires executable mode=mobility|generated_buff|light" in alt_report["errors"]


def test_reusable_gear_economy_contract_rejects_consumption_and_multi_yield() -> None:
    tool = _base_plan(
        "tool",
        _call("stats", "set_item_stats", resultKind="tool", damageClass="melee", damage=8, useTimeTicks=20, useAnimationTicks=20, maxStack=20, craftYield=20, consumable=True),
        _call("tool", "tool_capability", pickPower=55, miningSpeedScale=1.0),
    )
    report = runtime_plan_validation_report(tool)
    assert report["ok"] is False
    assert any("reusable tool" in error for error in report["errors"])
    repaired_fields = {
        field
        for detail in report["errorDetails"]
        if detail.get("callId") == "stats"
        for field in detail.get("repairParamNames", [])
    }
    assert repaired_fields == {"consumable", "maxStack", "craftYield"}
    assert all("resultKind" not in detail.get("repairParamNames", []) for detail in report["errorDetails"])

    armor = _base_plan(
        "armor",
        _call("stats", "set_item_stats", resultKind="armor", maxStack=1, craftYield=2, consumable=False),
        _call("armor", "armor_effect", armorSlot="head", stats={"defense": 4}),
    )
    report = runtime_plan_validation_report(armor)
    assert report["ok"] is False
    assert any("reusable armor" in error for error in report["errors"])

    missing_damage_tool = _base_plan(
        "tool",
        _call("stats", "set_item_stats", resultKind="tool", damageClass="melee", useTimeTicks=20, useAnimationTicks=20, maxStack=1, craftYield=1, consumable=False),
        _call("tool", "tool_capability", pickPower=55, miningSpeedScale=1.0),
        _call("root", "shoot_projectile", runtimeFamily="shoot", delivery="swing", movement="straight", speed=8, rangeTiles=25, lifetimeTicks=60, shotCount=1, spreadRadians=0, pierce=1, extraUpdates=0, homingStrength=0),
    )
    report = runtime_plan_validation_report(missing_damage_tool)
    assert report["ok"] is False
    assert any("combat set_item_stats requires explicit damage" in error for error in report["errors"])


def test_csharp_reusable_guard_preserves_authored_consumable_weapon_wire() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs").read_text(encoding="utf-8")
    assert 'Gameplay.Kind is "tool" or "armor" or "accessory"' in source
    assert 'Gameplay.Kind == "weapon" && !Gameplay.Consumable' in source
    assert "if (reusableGear)" in source
    assert "item.consumable = false;" in source
    assert "item.maxStack = 1;" in source


def test_permanent_http_errors_never_enter_transport_retry_lane() -> None:
    from infini_local.pipelines.llm_transport import _is_transport_error

    def error(status: int) -> HTTPError:
        return HTTPError("https://example.invalid", status, "test", Message(), None)

    assert _is_transport_error(error(400)) is False
    assert _is_transport_error(error(403)) is False
    assert _is_transport_error(error(404)) is False
    assert _is_transport_error(error(408)) is True
    assert _is_transport_error(error(429)) is True
    assert _is_transport_error(error(503)) is True


def test_compiled_tooltip_never_copies_core_mechanic_prose() -> None:
    data = {
        "category": "tool",
        "concept": {"coreMechanic": "Summons an immortal dragon and doubles every drop"},
        "gameplay": {"kind": "tool", "damage": 38, "pickPower": 110, "consumable": False},
        "attack": {
            "enabled": True, "runtimeFamily": "shoot", "delivery": "swing",
            "disableItemMeleeHitbox": False, "shotCount": 1, "movement": "straight", "pierce": 1,
        },
    }
    tooltip = compiled_runtime_tooltip(data)
    assert tooltip == "Executable: tool pick 110; item hitbox + shoot projectile (straight)."
    assert "dragon" not in tooltip.lower()
    assert "drop" not in tooltip.lower()


def test_compiled_shooting_sword_keeps_body_lane_and_truthful_tooltip() -> None:
    data = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damage=24, damageClass="melee", useTimeTicks=22, consumable=False, maxStack=1, craftYield=1),
        _call("root", "shoot_projectile", runtimeFamily="shoot", delivery="swing", movement="straight", speed=9, rangeTiles=30, lifetimeTicks=90, shotCount=2, spreadRadians=0.15, pierce=0),
    )
    report = runtime_plan_validation_report(data)
    assert report["ok"] is True
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["disableItemMeleeHitbox"] is False
    final_attack = {"enabled": True, **patch}
    final = {"category": "weapon", "gameplay": {"kind": "weapon", "damage": 24, "useTime": 22}, "attack": final_attack}
    tooltip = compiled_runtime_tooltip(final)
    assert "item hitbox + shoot projectile" in tooltip


def test_consumable_weapon_is_not_reusable_risk_and_multiple_roots_fail() -> None:
    balance = build_balance_report({
        "category": "weapon",
        "gameplay": {"kind": "weapon", "consumable": True, "maxStack": 30, "craftYield": 3, "damage": 18, "useTime": 25},
        "runtimePlan": {"resultKind": "consumable_weapon"},
    }, {})
    assert not any(risk.get("kind") == "reusable_gear_economy_invariant_broken" for risk in balance["reviewRisks"])

    root = _call("root-a", "shoot_projectile", runtimeFamily="shoot", delivery="shoot", movement="straight", damageClass="ranged", speed=8, rangeTiles=25, lifetimeTicks=80, shotCount=1, spreadRadians=0.0, pierce=0)
    extra = deepcopy(root)
    extra["callId"] = "root-b"
    data = {"runtimePlan": {"resultKind": "consumable_weapon", "engineCalls": [
        _call("stats", "set_item_stats", resultKind="consumable_weapon", damage=18, useTimeTicks=25, consumable=True, maxStack=30, craftYield=1),
        root,
        extra,
    ]}}
    report = runtime_plan_validation_report(data)
    assert report["ok"] is False
    assert any("extra root" in error for error in report["errors"])


def test_world_health_does_not_require_root_for_actual_ammo() -> None:
    data = {
        "name": "Ammo Probe",
        "tooltip": "Vanilla arrow carrier",
        "sourceMode": "generated",
        "category": "ammo",
        "gameplay": {"kind": "ammo"},
        "runtimePlan": {"resultKind": "ammo", "engineCalls": [_call("stats", "set_item_stats", resultKind="ammo", ammoFor="arrow")]},
        "debug": {"runtimePlanQuality": '{"hasStats":true,"hasRootExecutor":false}'},
    }
    health = build_recipe_health(data, app_version="test", visual_report={"ok": True, "slots": {}})
    assert "runtime_plan_invalid" not in health["problems"]


def test_item_vfx_events_survive_manifest_and_reject_wrong_renderer() -> None:
    assert _vfx_event_stage("on_use") == "active"
    assert _vfx_event_stage("on_alt_use") == "active"
    assert _vfx_event_stage("while_equipped") == "loop"
    data = _base_plan(
        "accessory",
        _call("stats", "set_item_stats", resultKind="accessory", maxStack=1, craftYield=1, consumable=False),
        _call("effect", "accessory_effect", archetype="mobility", stats={"movementSpeed": 0.1}),
        _call("cue", "visual_effect_cue", event="while_equipped", rendererKind="orbitingMotes", channel="ambientParticles", lane="support", textureRole="field", particleRole="child", emissionMode="orbit", particleSystemId="pl:glow", duration=24, repeatEvery=8, scale=0.8, density=0.35, alpha=0.7, spread=0.5, jitter=0.2, importance="secondary"),
    )
    assert runtime_plan_validation_report(deepcopy(data))["ok"] is True
    patch = compile_runtime_plan_to_genome_patch(deepcopy(data))
    item = {**deepcopy(data), "id": "equip-vfx", "attack": {"enabled": False, **patch}, "visual": {}}
    attach_hybrid_vfx_manifest(item, "equip-vfx")
    assert any(slot.get("event") == "while_equipped" and slot.get("eventGroup") == "item_live" for slot in item["vfxManifest"]["slots"])

    invalid = deepcopy(data)
    invalid["runtimePlan"]["engineCalls"][-1]["params"]["rendererKind"] = "beamLine"
    report = runtime_plan_validation_report(invalid)
    assert report["ok"] is False
    assert any("while_equipped rejects rendererKind=beamLine" in error for error in report["errors"])
    cue_details = [row for row in report["errorDetails"] if row.get("callId") == "cue"]
    assert cue_details
    assert {
        field
        for row in cue_details
        for field in row.get("repairParamNames", [])
    } == {"event", "rendererKind", "channel"}


def test_equipment_requires_dedicated_equip_overlay_asset_role(monkeypatch) -> None:
    from infini_local.pipelines import visual_sprite_generation as sprite_generation
    from infini_local.pipelines.visual_director_contract import visual_kit_projection_errors

    kit = canonical_visual_kit_view({
        "equipOverlayPrompt": "single cobalt circlet overlay with one central star gem",
        "bakedAssets": {"equip_overlay": {"mode": "baked_sprite", "reason": "runtime player identity"}},
    })
    data = {
        "id": "armor-overlay",
        "category": "armor",
        "gameplay": {"kind": "armor"},
        "attack": {"enabled": False, "runtimeFamily": "none"},
        "visual": {"preferredCanvasSize": 32, "imagePrompt": "helmet icon"},
        "visualKit": kit,
    }
    plan = build_visual_asset_plan(data)
    overlay = next(row for row in plan if row["role"] == "equip_overlay")
    assert overlay["required"] is True
    assert overlay["assetMode"] == "baked_sprite"
    assert overlay["canvas"] == 48

    missing = deepcopy(kit)
    missing["equipOverlayPrompt"] = ""
    assert visual_kit_projection_errors(missing, data)
    missing_role = deepcopy(kit)
    missing_role["bakedAssets"].pop("equip_overlay")
    assert visual_kit_projection_errors(missing_role, data)

    monkeypatch.setattr(sprite_generation, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(sprite_generation, "maybe_generate_sprite", lambda payload: payload)
    monkeypatch.setattr(sprite_generation, "write_visual_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sprite_generation,
        "generate_visual_asset",
        lambda *_args, **_kwargs: ("/tmp/equip-overlay.png", "/sprite/equip-overlay.png", 0.91, "generated"),
    )
    generated = sprite_generation.maybe_generate_visual_assets(deepcopy(data))
    assert generated["visual"]["equipOverlayPath"] == "/tmp/equip-overlay.png"
    assert generated["visual"]["equipOverlayStatus"] == "generated"


def test_sentry_root_body_and_child_shot_remain_separate_roles() -> None:
    data = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="summon", damage=24, useTimeTicks=30, useAnimationTicks=30, manaCost=10, maxStack=1, craftYield=1, consumable=False),
        _call("sentry", "deploy_sentry", placement="grounded", projectileShape="obsidian turret body", secondaryProjectileShape="small violet shard shot", movement="straight", speed=9, shotCount=1, spreadRadians=0, pierce=1, attackIntervalTicks=36, targetRangeTiles=28, helperLifetimeTicks=3600, secondaryLifetimeTicks=45, soundUseCatalogId="summon_sentry", soundImpactCatalogId="impact_magic", soundVolume=0.65),
    )
    boundary = runtime_plan_boundary_report(data)
    assert boundary["ok"] is True, boundary
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "sentry"
    assert patch["projectileShape"] == "obsidian turret body"
    assert patch["secondaryProjectileShape"] == "small violet shard shot"
    assert patch["maxChildProjectiles"] >= 1
    assert patch["soundUseCatalogId"] == "summon_sentry"
    assert patch["soundImpactCatalogId"] == "impact_magic"
    assert patch["soundVolume"] == 0.65

    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Visuals.cs").read_text(encoding="utf-8")
    assert "_runtimeVariant == GeneratedProjectileRuntimeVariant.Root" in source


def test_healing_potions_enable_vanilla_potion_sickness() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs"
    ).read_text(encoding="utf-8")
    assert "item.potion = Gameplay.HealLife > 0;" in source


def test_invalid_call_id_repair_is_indexed_identity_only() -> None:
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)
    from infini_local.pipelines.author_item_contract import (
        author_item_provider_targeted_repair_delta_schema,
        strict_author_item_targeted_repair_delta_report,
    )

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="magic", damage=20, useTimeTicks=20),
        _call("castStar", "cast_magic_weapon", family="bolt_staff", projectileFamily="star", speed=10, rangeTiles=40, lifetimeTicks=80, shotCount=1, spreadRadians=0, pierce=1),
    )
    failure = {"errors": [{
        "path": "$.runtimePlan.engineCalls[1].callId",
        "kind": "pattern",
        "expected": "^[a-z][a-z0-9_]{0,63}$",
        "actual": "castStar",
    }]}
    delta = {"engineCallIdPatches": [{
        "callIndex": 1,
        "currentCallId": "castStar",
        "fn": "cast_magic_weapon",
        "newCallId": "cast_star",
    }]}
    assert strict_author_item_targeted_repair_delta_report(delta)["ok"] is True
    provider_schema = author_item_provider_targeted_repair_delta_schema(
        allowed_call_id_repairs=[{
            "callIndex": 1,
            "currentCallId": "castStar",
            "fn": "cast_magic_weapon",
        }],
    )
    provider_properties = provider_schema["properties"]
    assert "engineCallParamPatches" not in provider_properties
    id_array = provider_properties["engineCallIdPatches"]
    assert id_array["type"] == "array"
    id_branch = id_array["items"]["anyOf"][0]
    assert id_branch["properties"]["callIndex"]["const"] == 1
    assert id_branch["properties"]["currentCallId"]["const"] == "castStar"
    assert id_branch["properties"]["fn"]["const"] == "cast_magic_weapon"
    repaired = author_item_repair_delta._apply_targeted_repair_delta(current, delta, failure)
    assert repaired["runtimePlan"]["engineCalls"][1] == {
        **current["runtimePlan"]["engineCalls"][1],
        "callId": "cast_star",
    }
    assert repaired["runtimePlan"]["engineCalls"][0] == current["runtimePlan"]["engineCalls"][0]

    # An invalid callId makes final-wire receipts unaddressable. Those missing
    # receipts are secondary evidence, not authorization to rewrite valid params.
    failure_with_receipt_noise = {
        "errors": [
            *failure["errors"],
            {
                "callId": "castStar",
                "fn": "cast_magic_weapon",
                "kind": "invalid_or_missing_call_id",
                "reason": "invalid_or_missing_call_id",
            },
            {
                "callId": "castStar",
                "fn": "cast_magic_weapon",
                "kind": "compiler_provenance_receipt_missing",
                "reason": "compiler_provenance_receipt_missing",
                "authoredParam": "speed",
            },
        ]
    }
    noisy_targets = author_item_repair_scope._repair_targets(failure_with_receipt_noise)
    assert author_item_repair_scope._targeted_repair_param_paths(
        current["runtimePlan"], noisy_targets
    ) == {}
    assert author_item_repair_scope._targeted_required_param_paths(
        current["runtimePlan"], noisy_targets
    ) == {}
    noisy_repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current, delta, failure_with_receipt_noise
    )
    assert noisy_repaired["runtimePlan"]["engineCalls"][1]["callId"] == "cast_star"
    assert noisy_repaired["runtimePlan"]["engineCalls"][1]["params"] == current["runtimePlan"]["engineCalls"][1]["params"]

    invalid = deepcopy(delta)
    invalid["engineCallIdPatches"][0]["newCallId"] = "stillCamelCase"
    assert strict_author_item_targeted_repair_delta_report(invalid)["ok"] is False

    wrong_owner = deepcopy(delta)
    wrong_owner["engineCallIdPatches"][0]["fn"] = "fire_ranged_weapon"
    try:
        author_item_repair_delta._apply_targeted_repair_delta(current, wrong_owner, failure)
    except Exception as exc:
        assert "cannot change fn" in str(exc)
    else:
        raise AssertionError("call-id repair changed the rejected call owner")

    duplicate = deepcopy(delta)
    duplicate["engineCallIdPatches"][0]["newCallId"] = "stats"
    try:
        author_item_repair_delta._apply_targeted_repair_delta(current, duplicate, failure)
    except Exception as exc:
        assert "duplicate callId" in str(exc)
    else:
        raise AssertionError("call-id repair created a duplicate stable id")


def test_targeted_author_field_repair_dossier_exposes_schema_limits() -> None:
    import json

    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    current = _base_plan(
        "weapon",
        _call(
            "stats",
            "set_item_stats",
            resultKind="weapon",
            damageClass="magic",
            damage=20,
            useTimeTicks=20,
        ),
    )
    current["concept"]["coreMechanic"] = "x" * 532
    failure = {
        "errors": [{
            "path": "$.concept.coreMechanic",
            "kind": "max_length",
            "actual": 532,
            "expected": 500,
        }]
    }

    request, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, failure
    )
    assert targeted is True
    dossier = json.loads(user_content)
    core_shape = dossier["targetedRepairDeltaShape"]["authorFields"]["coreMechanic"]
    assert core_shape == {
        "type": "string",
        "minLength": 2,
        "maxLength": 500,
    }
    response_schema = request["response_format"]["json_schema"]["schema"]
    author_fields = response_schema["properties"]["authorFields"]
    assert author_fields["type"] == "object"
    assert author_fields["properties"]["coreMechanic"]["type"] == "string"

    from infini_local.pipelines.author_item_contract import (
        normalize_author_item_targeted_repair_delta_text_limits,
        strict_author_item_targeted_repair_delta_report,
    )

    small_overshoot = {"authorFields": {"coreMechanic": "repair word " * 50}}
    normalized = normalize_author_item_targeted_repair_delta_text_limits(small_overshoot)
    assert small_overshoot["authorFields"]["coreMechanic"] == "repair word " * 50
    assert len(normalized["authorFields"]["coreMechanic"]) <= 500
    assert len(normalized["authorFields"]["coreMechanic"]) >= 450
    assert strict_author_item_targeted_repair_delta_report(normalized)["ok"] is True

    live_overshoot = {"authorFields": {"coreMechanic": "x" * 627}}
    live_normalized = normalize_author_item_targeted_repair_delta_text_limits(live_overshoot)
    assert len(live_normalized["authorFields"]["coreMechanic"]) <= 500
    assert strict_author_item_targeted_repair_delta_report(live_normalized)["ok"] is True

    large_overshoot = {"authorFields": {"coreMechanic": "x" * 700}}
    unchanged = normalize_author_item_targeted_repair_delta_text_limits(large_overshoot)
    assert len(unchanged["authorFields"]["coreMechanic"]) == 700
    assert strict_author_item_targeted_repair_delta_report(unchanged)["ok"] is False


def test_targeted_repair_dossier_keeps_required_object_valued_param() -> None:
    import json

    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    current = _base_plan(
        "armor",
        _call(
            "stats",
            "set_item_stats",
            resultKind="armor",
            damageClass="generic",
            damage=0,
            useTimeTicks=10,
            useAnimationTicks=14,
            armorSlot="head",
            defense=2,
            maxStack=1,
            craftYield=1,
            consumable=False,
        ),
        _call(
            "armor",
            "armor_effect",
            armorSlot="head",
            archetype="utility",
            defense=2,
            stats={"lightStrength": 1.0, "lightColorName": "orange"},
            setKey="",
            setBonus="invalid",
        ),
    )
    for index, call in enumerate(current["runtimePlan"]["engineCalls"]):
        call["_index"] = index
    failure = {"errors": [
        {
            "path": "$.runtimePlan.engineCalls[1].params.setBonus",
            "callId": "armor",
            "fn": "armor_effect",
            "kind": "runtime_validation",
            "reason": "setBonus must be a typed object",
            "repairParamNames": ["setBonus"],
        },
        {
            "callId": "armor",
            "reason": "compiler_provenance_receipt_missing",
            "authoredParam": "setBonus",
        },
        {
            "callId": "armor",
            "reason": "compiler_provenance_receipt_missing",
            "authoredParam": "setKey",
        },
    ]}

    request, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, failure
    )
    assert targeted is True
    dossier = json.loads(user_content)
    card = dossier["repairFunctionCards"]["armor"]
    assert card["requiredParamPaths"] == ["setBonus", "setKey"]
    assert set(card["params"]) == {"setBonus", "setKey"}
    assert card["params"]["setBonus"]["type"] == "object"
    assert card["params"]["setBonus"]["additionalProperties"] is False
    response_schema = request["response_format"]["json_schema"]["schema"]
    patch_property = response_schema["properties"]["engineCallParamPatches"]
    assert patch_property["type"] == "array"
    patch_array = patch_property
    patch_branches = patch_array["items"]["anyOf"]
    armor_branch = next(
        branch
        for branch in patch_branches
        if branch["properties"]["callId"]["const"] == "armor"
    )
    assert set(armor_branch["properties"]["params"]["required"]) == {"setBonus", "setKey"}


def test_missing_combat_stats_call_uses_existing_full_redesign_lane() -> None:
    import json

    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    current = _base_plan(
        "weapon",
        _call(
            "root",
            "shoot_projectile",
            runtimeFamily="returning",
            delivery="throw",
            movement="boomerang",
            speed=10,
            rangeTiles=40,
            lifetimeTicks=3600,
            shotCount=1,
            spreadRadians=0,
            pierce=-1,
            damage=22,
            damageClass="melee",
            useTimeTicks=20,
        ),
    )
    current["runtimePlan"]["engineCalls"][0]["_index"] = 0
    failure = {"errors": [
        {
            "path": "$.runtimePlan.engineCalls",
            "kind": "runtime_validation",
            "reason": "combat result lacks set_item_stats",
        },
        {
            "path": "$.runtimePlan.engineCalls[0].params.damage",
            "callId": "root",
            "fn": "shoot_projectile",
            "kind": "additional_property",
            "reason": "damage is not a shoot_projectile param",
            "authoredParam": "damage",
        },
    ]}

    request, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, failure
    )

    assert targeted is False
    dossier = json.loads(user_content)
    assert dossier["repairMode"] == "full_redesign"
    assert "runtimePlan" in dossier["requiredPatchKeys"]
    assert "engineCalls" in dossier["requiredRuntimePlanKeys"]
    assert request["response_format"]["type"] == "json_object"


def test_numeric_zero_call_id_keeps_indexed_owner_for_targeted_id_repair() -> None:
    import json

    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request
    from infini_local.pipelines.combine_validation import _strict_authoring_validation

    current = _base_plan(
        "weapon",
        _call(
            "temporary",
            "set_item_stats",
            resultKind="weapon",
            damageClass="melee",
            damage=22,
            useTimeTicks=40,
        ),
        _call(
            "root",
            "shoot_projectile",
            delivery="shoot",
            movement="straight",
            speed=10,
            rangeTiles=20,
            lifetimeTicks=120,
            shotCount=1,
            spreadRadians=0,
            pierce=1,
            runtimeFamily="shoot",
        ),
    )
    current["runtimePlan"]["engineCalls"][0]["callId"] = 0
    current["runtimePlan"]["engineCalls"][1]["callId"] = 1
    with __import__("pytest").raises(PlannerUnavailable) as captured:
        _strict_authoring_validation(current)
    failure = {"errors": captured.value.author_repair_targets}

    request, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, failure
    )

    assert targeted is True
    dossier = json.loads(user_content)
    id_shape = dossier["targetedRepairDeltaShape"]["engineCallIdPatches"]
    assert id_shape == [{
        "callIndex": "exact rejected index",
        "currentCallId": "exact rejected id",
        "fn": "same accepted fn",
        "newCallId": "new valid snake_case id",
    }]
    id_target = next(
        target
        for target in dossier["invalidTargets"]
        if target.get("path") == "$.runtimePlan.engineCalls[0].callId"
    )
    assert id_target["callId"] == "0"
    response_schema = request["response_format"]["json_schema"]["schema"]
    id_property = response_schema["properties"]["engineCallIdPatches"]
    assert id_property["type"] == "array"
    id_array = id_property
    assert id_array["minItems"] == 2
    assert id_array["maxItems"] == 2


def test_cross_field_repair_dependencies_are_atomic() -> None:
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)
    from infini_local.pipelines.llm_authoring_prompt import sharp_engine_fn_catalog_for_llm
    from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model

    delivery_schema = engine_params_model("shoot_projectile").model_json_schema()["properties"]["delivery"]
    delivery_enum = next(
        branch["enum"]
        for branch in delivery_schema["anyOf"]
        if "enum" in branch
    )
    assert {"flail", "yoyo", "whip"}.issubset(set(delivery_enum))
    movement_schema = engine_params_model("shoot_projectile").model_json_schema()["properties"]["movement"]
    movement_enum = next(branch["enum"] for branch in movement_schema["anyOf"] if "enum" in branch)
    assert {"flail_tether", "yoyo_hover", "whip_lash"}.issubset(set(movement_enum))

    current = _base_plan(
        "weapon",
        _call(
            "stats",
            "set_item_stats",
            resultKind="weapon",
            damageClass="melee",
            damage=28,
            useTimeTicks=18,
            maxStack=1,
            craftYield=1,
            consumable=False,
        ),
        _call(
            "throw_logic",
            "shoot_projectile",
            runtimeFamily="boomerang",
            delivery="swing",
            movement="boomerang",
            speed=12,
            rangeTiles=30,
            lifetimeTicks=120,
            shotCount=1,
            spreadRadians=0.0,
            pierce=-1,
        ),
    )
    failure = {
        "errors": [{
            "path": "$.runtimePlan.engineCalls[1].params.runtimeFamily",
            "kind": "literal_error",
            "reason": "runtimeFamily must use a canonical value",
        }],
    }
    targets = author_item_repair_scope._resolve_indexed_target_call_owners(
        author_item_repair_scope._repair_targets(failure),
        current["runtimePlan"],
    )
    cards = author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"],
        targets,
        sharp_engine_fn_catalog_for_llm(),
    )
    assert set(cards["throw_logic"]["params"]) == {"runtimeFamily", "delivery", "movement"}
    assert cards["throw_logic"]["requiredTogether"] == [["delivery", "movement", "runtimeFamily"]]
    assert {"runtimeFamily": "returning", "delivery": "throw", "movement": "boomerang"} in cards["throw_logic"]["allowedTogetherValues"]
    assert {"runtimeFamily": "returning", "delivery": "swing", "movement": "boomerang"} not in cards["throw_logic"]["allowedTogetherValues"]

    try:
        author_item_repair_delta._apply_targeted_repair_delta(
            current,
            {"engineCallParamPatches": [{
                "callId": "throw_logic",
                "fn": "shoot_projectile",
                "params": {"runtimeFamily": "returning"},
            }]},
            failure,
        )
    except Exception as exc:
        assert "incomplete_dependency_group" in str(exc)
    else:
        raise AssertionError("cross-field repair accepted a partial dependency group")

    try:
        author_item_repair_delta._apply_targeted_repair_delta(
            current,
            {"engineCallParamPatches": [{
                "callId": "throw_logic",
                "fn": "shoot_projectile",
                "params": {"runtimeFamily": "returning", "delivery": "swing", "movement": "boomerang"},
            }]},
            failure,
        )
    except Exception as exc:
        assert "incompatible_dependency_group" in str(exc)
    else:
        raise AssertionError("cross-field repair accepted an incompatible pair")

    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current,
        {"engineCallParamPatches": [{
            "callId": "throw_logic",
            "fn": "shoot_projectile",
            "params": {"runtimeFamily": "returning", "delivery": "throw", "movement": "boomerang"},
        }]},
        failure,
    )
    assert repaired["runtimePlan"]["engineCalls"][1]["params"] == {
        "runtimeFamily": "returning",
        "delivery": "throw",
        "movement": "boomerang",
        "speed": 12,
        "rangeTiles": 30,
        "lifetimeTicks": 120,
        "shotCount": 1,
        "spreadRadians": 0.0,
        "pierce": -1,
    }


def test_call_level_rejection_uses_full_same_author_repair_contract() -> None:
    import json

    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="magic", damage=18, useTimeTicks=25),
        _call("cast", "cast_magic_weapon", family="staff", projectileFamily="bolt", speed=9, rangeTiles=45, lifetimeTicks=60, shotCount=1, spreadRadians=0.1, pierce=1),
        _call("helper", "spawn_temporary_helper_projectile", family="pet_attack", movement="orbit", speed=6, rangeTiles=12, lifetimeTicks=300, shotCount=1, spreadRadians=0, pierce=3),
    )
    current["runtimePlan"]["engineCalls"][1]["params"]["futureBad"] = 1
    failure = {"runtimeValidation": {"errorDetails": [
        {
            "path": "$.runtimePlan.engineCalls[2]",
            "callId": "helper",
            "fn": "spawn_temporary_helper_projectile",
            "kind": "runtime_validation",
            "reason": "runtime supports one root executor; extra root",
        },
        {
            "path": "$.runtimePlan.engineCalls[1].params.futureBad",
            "callId": "cast",
            "fn": "cast_magic_weapon",
            "kind": "additional_property",
            "reason": "Extra inputs are not permitted",
        },
    ]}}
    request, user_content, _, targeted, _ = build_same_author_repair_request(
        current,
        {"name": "Baby Bird Staff"},
        {"name": "Lens"},
        failure,
    )
    dossier = json.loads(user_content)
    assert targeted is False
    assert dossier["repairMode"] == "full_redesign"
    assert dossier["invalidTargets"][0]["callId"] == "helper"
    assert request["response_format"]["type"] == "json_object"
    assert set(dossier["requiredPatchKeys"]) == {
        "category", "coreMechanic", "primaryVerb", "controlStyle", "runtimePlan",
    }
    assert set(dossier["requiredRuntimePlanKeys"]) == {
        "resultKind", "engineCalls", "runtimeStateIntent", "sourceReading",
        "balanceIntent", "anomalyFlags",
    }
    assert request["response_format"] == {"type": "json_object"}
    assert any(
        "top category is weapon only for consumable_weapon" in rule
        for rule in dossier["patchRules"]
    )
    assert (
        "runtimePlan.resultKind must match set_item_stats.params.resultKind and category when category is repairable."
        not in dossier["patchRules"]
    )


def test_generated_buff_alt_cooldown_reaches_final_wire_and_csharp_runtime() -> None:
    from pathlib import Path

    from infini_local.core.runtime_authoring.final_projection import (
        attach_runtime_final_evidence,
        compile_runtime_plan_to_final_result,
    )

    authored = _base_plan(
        "accessory",
        _call("stats", "set_item_stats", resultKind="accessory", damageClass="generic", damage=0, useTimeTicks=60, maxStack=1, craftYield=1, consumable=False),
        _call(
            "alt_buff",
            "set_alt_use_mode",
            mode="generated_buff",
            generatedBuff={"durationTicks": 600, "lifeRegen": 10},
            cooldownTicks=3600,
        ),
    )
    patch = compile_runtime_plan_to_genome_patch(authored)
    assert patch["altUseMode"] == "generated_buff"
    assert patch["altUseCooldownTicks"] == 3600
    assert patch["altGeneratedBuff"]["lifeRegen"] == 10

    output = {
        "gameplay": {
            "kind": "accessory",
            "damageClass": "generic",
            "damage": 0,
            "useTime": 60,
            "maxStack": 1,
            "craftYield": 1,
            "consumable": False,
            "altUseMode": "generated_buff",
            "altUseCooldownTicks": 3600,
            "altGeneratedBuff": {"durationTicks": 600, "lifeRegen": 10},
        },
        "runtimeContract": {"primaryVerb": "equip", "controlStyle": "passive"},
    }
    attach_runtime_final_evidence(output, compile_runtime_plan_to_final_result(authored))
    cooldown_receipt = next(
        row
        for row in output["runtimeContract"]["finalWireReceipts"]
        if row["callId"] == "alt_buff" and row["authoredParam"] == "cooldownTicks"
    )
    assert cooldown_receipt["compiledField"] == "altUseCooldownTicks"
    assert cooldown_receipt["finalPath"] == "gameplay.altUseCooldownTicks"
    assert cooldown_receipt["status"] == "active"

    root = Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal"
    model = (root / "Common/Models/GeneratedItemData.Model.cs").read_text(encoding="utf-8")
    item = (root / "Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    multiplayer = (root / "Common/Players/InfiniCraftPlayer.Multiplayer.cs").read_text(encoding="utf-8")
    assert "public int AltUseCooldownTicks" in model
    assert "StartGeneratedAltUseCooldown(gp.AltUseCooldownTicks)" in item
    assert "StartGeneratedAltUseCooldown(gp.AltUseCooldownTicks)" in multiplayer
    assert "_generatedAltUseCooldownTicks > 0" in multiplayer


def test_sound_repair_schema_uses_only_executable_catalog_ids() -> None:
    from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
    from infini_local.core.sound_catalog import IMPACT_SOUND_IDS, USE_SOUND_IDS

    schema = engine_params_model("fire_ranged_weapon").model_json_schema()["properties"]
    use_enum = next(
        branch["enum"]
        for branch in schema["soundUseCatalogId"]["anyOf"]
        if "enum" in branch
    )
    impact_enum = next(
        branch["enum"]
        for branch in schema["soundImpactCatalogId"]["anyOf"]
        if "enum" in branch
    )
    assert set(use_enum) == set(USE_SOUND_IDS)
    assert set(impact_enum) == set(IMPACT_SOUND_IDS)
    assert "shotgun_heavy" in use_enum
    assert "firearm_heavy" not in use_enum


def test_targeted_repair_requires_every_exact_leaf_across_calls() -> None:
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)
    from infini_local.pipelines.author_item_contract import (
        author_item_provider_targeted_repair_delta_schema,
    )
    from infini_local.pipelines.llm_authoring_prompt import sharp_engine_fn_catalog_for_llm

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="ranged", damage=12),
        _call(
            "root",
            "shoot_projectile",
            runtimeFamily="shoot",
            delivery="shoot",
            movement="straight",
            speed=10,
            rangeTiles=30,
            lifetimeTicks=60,
            shotCount=1,
            spreadRadians=0,
            pierce=1,
        ),
    )
    failure = {"errors": [
        {"path": "$.runtimePlan.engineCalls[0].params.damage", "reason": "invalid damage"},
        {"path": "$.runtimePlan.engineCalls[1].params.pierce", "reason": "missing pierce"},
    ]}
    targets = author_item_repair_scope._resolve_indexed_target_call_owners(
        author_item_repair_scope._repair_targets(failure),
        current["runtimePlan"],
    )
    cards = author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"], targets, sharp_engine_fn_catalog_for_llm(),
    )
    assert cards["stats"]["requiredParamPaths"] == ["damage"]
    assert cards["root"]["requiredParamPaths"] == ["pierce"]
    patch_field = author_item_provider_targeted_repair_delta_schema(cards)["properties"][
        "engineCallParamPatches"
    ]
    patch_array = next(
        branch
        for branch in patch_field.get("anyOf", [patch_field])
        if branch.get("type") == "array"
    )
    assert patch_array["minItems"] == 2

    partial = {"engineCallParamPatches": [{
        "callId": "stats", "fn": "set_item_stats", "params": {"damage": 14},
    }]}
    try:
        author_item_repair_delta._apply_targeted_repair_delta(current, partial, failure)
    except Exception as exc:
        assert "omits required_exact_param:root:pierce" in str(exc)
    else:
        raise AssertionError("targeted repair accepted an omitted exact leaf")

    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current,
        {"engineCallParamPatches": [
            {"callId": "stats", "fn": "set_item_stats", "params": {"damage": 14}},
            {"callId": "root", "fn": "shoot_projectile", "params": {"pierce": 2}},
        ]},
        failure,
    )
    assert repaired["runtimePlan"]["engineCalls"][0]["params"]["damage"] == 14
    assert repaired["runtimePlan"]["engineCalls"][1]["params"]["pierce"] == 2


def test_targeted_repair_routes_missing_root_family_and_additional_param_atomically() -> None:
    from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)
    from infini_local.pipelines.llm_authoring_prompt import sharp_engine_fn_catalog_for_llm

    missing_family = _base_plan(
        "consumable_weapon",
        _call(
            "stats", "set_item_stats", resultKind="consumable_weapon",
            damageClass="ranged", damage=20, useTimeTicks=30,
            useAnimationTicks=30, consumable=True, maxStack=99, craftYield=1,
        ),
        _call(
            "root", "shoot_projectile", delivery="throw", movement="gravity_arc",
            speed=8, rangeTiles=40, lifetimeTicks=120, shotCount=1,
            spreadRadians=0, pierce=1,
        ),
    )
    report = runtime_plan_validation_report(deepcopy(missing_family))
    targets = author_item_repair_scope._resolve_indexed_target_call_owners(
        author_item_repair_scope._repair_targets({"runtimeValidation": report}),
        missing_family["runtimePlan"],
    )
    cards = author_item_repair_scope._targeted_repair_function_cards(
        missing_family["runtimePlan"], targets, sharp_engine_fn_catalog_for_llm(),
    )
    assert cards["root"]["requiredParamPaths"] == [
        "delivery", "movement", "runtimeFamily",
    ]

    sentry = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="summon", damage=15),
        _call("sentry", "deploy_sentry", lifetimeTicks=1800),
    )
    sentry_failure = {"authorRepairTargets": [
        {
            "kind": "runtime_validation",
            "path": "$.runtimePlan.engineCalls[1].params.lifetimeTicks",
            "reason": "engineCalls.1.params.lifetimeTicks: Extra inputs are not permitted",
        },
        {
            "kind": "runtime_validation",
            "path": "$.runtimePlan.engineCalls[1].params.movement",
            "repairParamNames": ["movement"],
        },
    ]}
    sentry_targets = author_item_repair_scope._resolve_indexed_target_call_owners(
        author_item_repair_scope._repair_targets(sentry_failure),
        sentry["runtimePlan"],
    )
    assert author_item_repair_scope._targeted_param_delete_specs(
        sentry["runtimePlan"], sentry_targets,
    ) == [{"callId": "sentry", "fn": "deploy_sentry", "paramPaths": ["lifetimeTicks"]}]
    sentry_cards = author_item_repair_scope._targeted_repair_function_cards(
        sentry["runtimePlan"], sentry_targets, sharp_engine_fn_catalog_for_llm(),
    )
    assert sentry_cards["sentry"]["requiredParamPaths"] == ["movement"]
    assert "lifetimeTicks" not in sentry_cards["sentry"]["params"]
    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        sentry,
        {
            "engineCallParamDeletes": [
                {"callId": "sentry", "fn": "deploy_sentry", "paramPaths": ["lifetimeTicks"]},
            ],
            "engineCallParamPatches": [
                {"callId": "sentry", "fn": "deploy_sentry", "params": {"movement": "straight"}},
            ],
        },
        sentry_failure,
    )
    sentry_params = repaired["runtimePlan"]["engineCalls"][1]["params"]
    assert "lifetimeTicks" not in sentry_params
    assert sentry_params["movement"] == "straight"


def test_strict_validation_carries_all_structured_repair_targets() -> None:
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)
    from infini_local.pipelines.author_item_contract import (
        author_item_provider_targeted_repair_delta_schema,
    )
    from infini_local.pipelines.combine_validation import _strict_authoring_validation
    from infini_local.pipelines.llm_authoring_prompt import sharp_engine_fn_catalog_for_llm

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="magic", damage="18"),
        _call(
            "root", "shoot_projectile", runtimeFamily="shoot", delivery="shoot",
            movement="straight", speed="12", rangeTiles=30, lifetimeTicks=60,
            shotCount=1, spreadRadians=0, pierce=1,
        ),
        _call(
            "hit", "apply_on_hit_effect", onHit="burn", count="3",
            secondaryDamageMultiplier="0.5", secondaryLifetimeTicks="30", debuffTime="120",
        ),
        _call(
            "child", "spawn_secondary_projectiles", trigger="on_hit", count="3",
            damageMultiplier="0.5", spreadRadians="0.8", lifetimeTicks="30",
            projectileShape="light_shard",
        ),
    )
    current.update({
        "name": "Typed Repair Carrier",
        "concept": {"fantasy": "f", "mergeLogic": "m", "coreMechanic": "c"},
        "runtimeContract": {"primaryVerb": "fire", "controlStyle": "tap"},
    })
    current["_authorItemRaw"] = deepcopy(current)
    try:
        _strict_authoring_validation(current)
    except PlannerUnavailable as exc:
        repair_targets = exc.author_repair_targets
    else:
        raise AssertionError("string-typed engine params passed strict validation")

    target_paths = {str(row.get("path") or "") for row in repair_targets}
    for index in range(4):
        assert any(f"engineCalls[{index}].params." in path for path in target_paths)
    failure = {"authorRepairTargets": repair_targets}
    targets = author_item_repair_scope._resolve_indexed_target_call_owners(
        author_item_repair_scope._repair_targets(failure), current["runtimePlan"],
    )
    cards = author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"], targets, sharp_engine_fn_catalog_for_llm(),
    )
    patch_field = author_item_provider_targeted_repair_delta_schema(cards)["properties"][
        "engineCallParamPatches"
    ]
    patch_array = next(
        branch
        for branch in patch_field.get("anyOf", [patch_field])
        if branch.get("type") == "array"
    )
    assert patch_array["minItems"] == 4


def test_vfx_repair_dependency_group_uses_executable_triples() -> None:
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)
    from infini_local.pipelines.llm_authoring_prompt import sharp_engine_fn_catalog_for_llm

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="summon", damage=22),
        _call(
            "root", "perform_melee_attack", family="whip", speed=10,
            rangeTiles=12, lifetimeTicks=30, pierce=-1, useTimeTicks=30,
            shotCount=1, spreadRadians=0,
        ),
        _call(
            "vfx", "visual_effect_cue", event="on_use",
            rendererKind="spriteStampTrail", channel="motionTrail",
            particleSystemId="pl:glow", duration=20,
        ),
    )
    failure = {"errors": [
        {"path": "$.runtimePlan.engineCalls[2].params.event", "reason": "invalid cue triple"},
        {"path": "$.runtimePlan.engineCalls[2].params.rendererKind", "reason": "invalid cue triple"},
        {"path": "$.runtimePlan.engineCalls[2].params.channel", "reason": "invalid cue triple"},
    ]}
    targets = author_item_repair_scope._resolve_indexed_target_call_owners(
        author_item_repair_scope._repair_targets(failure), current["runtimePlan"],
    )
    cards = author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"], targets, sharp_engine_fn_catalog_for_llm(),
    )
    rows = cards["vfx"]["allowedTogetherValues"]
    assert rows
    assert {row["event"] for row in rows} == {"on_use"}
    assert {
        ("on_use", "childMotes", "ambientParticles"),
        ("on_use", "impactRing", "impactShape"),
        ("on_use", "lightCue", "light"),
        ("on_use", "soundCue", "sound"),
    } == {(row["event"], row["rendererKind"], row["channel"]) for row in rows}

    invalid_delta = {"engineCallParamPatches": [{
        "callId": "vfx",
        "fn": "visual_effect_cue",
        "params": {
            "event": "while_held",
            "rendererKind": "particleEmitter",
            "channel": "ambient",
        },
    }]}
    try:
        author_item_repair_delta._apply_targeted_repair_delta(current, invalid_delta, failure)
    except Exception as exc:
        assert "incompatible_dependency_group:vfx" in str(exc)
    else:
        raise AssertionError("targeted repair accepted an incompatible VFX triple")

    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current,
        {"engineCallParamPatches": [{
            "callId": "vfx",
            "fn": "visual_effect_cue",
            "params": {
                "event": "on_use",
                "rendererKind": "childMotes",
                "channel": "ambientParticles",
            },
        }]},
        failure,
    )
    assert repaired["runtimePlan"]["engineCalls"][2]["params"]["rendererKind"] == "childMotes"


def test_full_redesign_provider_schema_keeps_required_plan_non_nullable() -> None:
    from infini_local.pipelines.author_item_contract import (
        author_item_provider_repair_response_schema,
        author_item_provider_response_schema,
    )

    initial = author_item_provider_response_schema()
    allowed = {
        "category", "coreMechanic", "primaryVerb", "controlStyle",
        "playerViewTimeline", "runtimePlan",
    }
    repair = author_item_provider_repair_response_schema(allowed)
    assert set(repair["properties"]) == allowed
    assert set(repair["required"]) == allowed
    assert any(
        branch.get("type") == "null"
        for branch in repair["properties"]["playerViewTimeline"]["anyOf"]
    )
    repair_plan = repair["properties"]["runtimePlan"]
    assert repair_plan["type"] == "object"
    assert repair_plan["properties"]["engineCalls"]["type"] == "array"
    assert set(repair_plan["required"]) == {
        "resultKind", "engineCalls", "runtimeStateIntent", "sourceReading",
        "balanceIntent", "anomalyFlags",
    }

    def schema_depth(value: object) -> int:
        if isinstance(value, dict):
            return 1 + max((schema_depth(child) for child in value.values()), default=0)
        if isinstance(value, list):
            return 1 + max((schema_depth(child) for child in value), default=0)
        return 0

    assert schema_depth(repair) <= schema_depth(initial)


def test_full_redesign_uses_large_stage_json_object_transport(monkeypatch) -> None:
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
    llm_transport,
)

    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", "auto")
    current = _base_plan(
        "tool",
        _call("stats", "set_item_stats", resultKind="tool", damageClass="melee", damage=18),
        _call("tool", "tool_capability", pickPower=115, miningSpeedScale=1.0),
        _call("hit", "apply_on_hit_effect", onHit="burn", debuffTime=120),
    )
    current.update({
        "name": "Obsidian Tool",
        "concept": {"fantasy": "f", "mergeLogic": "m", "coreMechanic": "c"},
        "runtimeContract": {"primaryVerb": "mine", "controlStyle": "automatic"},
    })
    failure = {"authorRepairTargets": [{
        "path": "$.runtimePlan.engineCalls[2]",
        "callId": "hit",
        "fn": "apply_on_hit_effect",
        "reason": "executor_not_representable: tool cannot execute combat call",
    }]}
    request, user_content, _, targeted, _ = author_item_repair.build_same_author_repair_request(
        current, {"name": "Pickaxe"}, {"name": "Obsidian"}, failure,
    )
    assert targeted is False
    assert request["response_format"] == {"type": "json_object"}
    dossier = __import__("json").loads(user_content)
    assert set(dossier["requiredPatchKeys"]) == {
        "category", "coreMechanic", "primaryVerb", "controlStyle", "runtimePlan",
    }
    assert set(dossier["requiredRuntimePlanKeys"]) == {
        "resultKind", "engineCalls", "runtimeStateIntent", "sourceReading",
        "balanceIntent", "anomalyFlags",
    }


def test_full_redesign_unions_concurrent_visual_target_surface() -> None:
    import json

    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    current = _base_plan(
        "weapon",
        _call(
            "stats", "set_item_stats", resultKind="weapon", damageClass="melee",
            damage=18, useTimeTicks=24, maxStack=1, craftYield=1, consumable=False,
        ),
        _call(
            "root", "perform_melee_attack", family="swing", speed=10,
            rangeTiles=10, lifetimeTicks=24, pierce=1, useTimeTicks=24,
            shotCount=1, spreadRadians=0,
        ),
    )
    current["runtimePlan"]["visualIntent"].pop("impact")
    failure = {"authorRepairTargets": [
        {
            "path": "$.runtimePlan.visualIntent.impact",
            "kind": "required",
            "reason": "Field required",
        },
        {
            "path": "$.runtimePlan.engineCalls",
            "kind": "parent_economy_unrepresentable_mechanic",
            "reason": "unrepresentable_mechanic: reusable gear parent cannot become consumable",
        },
    ]}
    _, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {"name": "Spear", "damage": 8, "consumable": False},
        {"name": "Rope", "damage": 0}, failure,
    )
    dossier = json.loads(user_content)
    assert targeted is False
    assert dossier["repairMode"] == "full_redesign"
    assert "visualIntent" in dossier["allowedPatchKeys"]
    assert any(
        target["path"] == "$.runtimePlan.visualIntent.impact"
        for target in dossier["invalidTargets"]
    )
    assert "Do not return visualIntent" not in " ".join(dossier["patchRules"])


def test_generated_buff_alt_use_requires_explicit_positive_cooldown() -> None:
    from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report

    current = _base_plan(
        "accessory",
        _call(
            "stats", "set_item_stats", resultKind="accessory", damageClass="generic",
            damage=0, useTimeTicks=60, maxStack=1, craftYield=1, consumable=False,
        ),
        _call(
            "alt", "set_alt_use_mode", mode="generated_buff", durationTicks=600,
            generatedBuff={"durationTicks": 600, "lifeRegen": 5},
        ),
    )
    report = runtime_plan_validation_report(current)
    detail = next(
        row for row in report["errorDetails"]
        if "requires explicit positive cooldownTicks" in str(row.get("reason"))
    )
    assert detail["callId"] == "alt"
    assert detail["fn"] == "set_alt_use_mode"
    assert detail["repairParamNames"] == ["cooldownTicks"]

    current["runtimePlan"]["engineCalls"][1]["params"]["cooldownTicks"] = 600
    repaired = runtime_plan_validation_report(current)
    assert not any("requires explicit positive cooldownTicks" in error for error in repaired["errors"])


def test_whip_requires_summon_melee_speed_damage_class() -> None:
    from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report

    current = _base_plan(
        "weapon",
        _call(
            "stats", "set_item_stats", resultKind="weapon",
            damageClass="melee", damage=22, useTimeTicks=30,
        ),
        _call(
            "root", "perform_melee_attack", family="whip", speed=10,
            rangeTiles=12, lifetimeTicks=30, pierce=-1, useTimeTicks=30,
            shotCount=1, spreadRadians=0,
        ),
    )
    report = runtime_plan_validation_report(current)
    detail = next(
        row for row in report["errorDetails"]
        if "runtimeFamily=whip requires damageClass=summon_melee_speed" in str(row.get("reason"))
    )
    assert detail["callId"] == "stats"
    assert detail["fn"] == "set_item_stats"
    assert detail["repairParamNames"] == ["damageClass"]

    current["runtimePlan"]["engineCalls"][0]["params"]["damageClass"] = "summon_melee_speed"
    repaired = runtime_plan_validation_report(current)
    assert not any("runtimeFamily=whip requires damageClass" in error for error in repaired["errors"])


def test_consumable_weapon_cannot_spend_explicit_reusable_gear_parent() -> None:
    import json

    from infini_local.pipelines.combine_validation import _consumable_parent_economy_report
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    spear = {
        "name": "Spear", "damage": 8, "consumable": False,
        "accessory": False, "headSlot": -1, "bodySlot": -1, "legSlot": -1,
    }
    rope = {
        "name": "Rope", "damage": -1, "consumable": True,
        "accessory": False, "headSlot": -1, "bodySlot": -1, "legSlot": -1,
    }
    current = _base_plan(
        "consumable_weapon",
        _call(
            "stats", "set_item_stats", resultKind="consumable_weapon",
            damageClass="ranged", damage=14, useTimeTicks=25,
            maxStack=99, craftYield=1, consumable=True,
        ),
        _call(
            "root", "shoot_projectile", runtimeFamily="throw", delivery="throw",
            movement="gravity_arc", speed=10, rangeTiles=25, lifetimeTicks=60,
            shotCount=1, spreadRadians=0, pierce=2,
        ),
    )
    current.update({
        "name": "Rope Spear",
        "concept": {"fantasy": "f", "mergeLogic": "m", "coreMechanic": "c"},
        "runtimeContract": {"primaryVerb": "throw", "controlStyle": "tap"},
    })
    report = _consumable_parent_economy_report(current, spear, rope)
    assert report["ok"] is False
    assert report["reusableGearParents"] == ["Spear"]

    target = {
        "path": "$.runtimePlan.engineCalls",
        "kind": "parent_economy_unrepresentable_mechanic",
        "reason": (
            "unrepresentable_mechanic: consumable_weapon cannot spend reusable gear "
            "parent(s): Spear; full redesign must preserve reusable gear economy"
        ),
        "reusableGearParents": ["Spear"],
    }
    _, user_content, _, targeted, _ = build_same_author_repair_request(
        current, spear, rope, {"authorRepairTargets": [target]},
    )
    assert targeted is False
    assert json.loads(user_content)["repairMode"] == "full_redesign"

    grenade = {**spear, "name": "Grenade", "consumable": True}
    gel = {**rope, "name": "Gel"}
    allowed = _consumable_parent_economy_report(current, grenade, gel)
    assert allowed["ok"] is True
    assert allowed["applicable"] is False


def test_sole_typed_armor_parent_cannot_collapse_into_weapon() -> None:
    import json

    from infini_local.pipelines.combine_validation import _parent_role_preservation_report
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    helmet = {
        "name": "Mining Helmet", "damage": -1, "accessory": False,
        "headSlot": 11, "bodySlot": -1, "legSlot": -1,
    }
    torch = {
        "name": "Torch", "damage": -1, "accessory": False,
        "headSlot": -1, "bodySlot": -1, "legSlot": -1,
    }
    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon"),
        _call("root", "shoot_projectile", runtimeFamily="throw", delivery="throw", movement="gravity_arc"),
    )
    current.update({
        "name": "Miner's Torch",
        "concept": {"fantasy": "f", "mergeLogic": "m", "coreMechanic": "c"},
        "runtimeContract": {"primaryVerb": "throw", "controlStyle": "tap"},
    })
    report = _parent_role_preservation_report(current, helmet, torch)
    assert report == {
        "ok": False,
        "applicable": True,
        "parentStrongRoles": ["armor"],
        "expectedResultKind": "armor",
        "expectedArmorSlots": ["head"],
        "actualResultKind": "weapon",
        "actualArmorSlot": "",
    }
    target = {
        "path": "$.runtimePlan.engineCalls",
        "kind": "parent_role_unrepresentable_mechanic",
        "reason": (
            "unrepresentable_mechanic: sole strong parent role is armor; "
            "full redesign requires resultKind=armor and armorSlot=head"
        ),
        "expectedResultKind": "armor",
        "expectedArmorSlots": ["head"],
    }
    _, user_content, _, targeted, _ = build_same_author_repair_request(
        current, helmet, torch, {"authorRepairTargets": [target]},
    )
    assert targeted is False
    assert json.loads(user_content)["repairMode"] == "full_redesign"

    valid = _base_plan(
        "armor",
        _call("stats", "set_item_stats", resultKind="armor", armorSlot="head"),
        _call("effect", "armor_effect", slot="head", stats={"lightStrength": 1.0, "lightColorName": "yellow"}),
    )
    assert _parent_role_preservation_report(valid, helmet, torch)["ok"] is True

    weapon_parent = {**torch, "damage": 10}
    mixed = _parent_role_preservation_report(current, helmet, weapon_parent)
    assert mixed["ok"] is True
    assert mixed["applicable"] is False


def test_provenance_mismatch_projects_compiled_values_as_repair_consts() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import ENGINE_FUNCTION_CATALOG
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", ammoFor="empty"),
        _call("root", "fire_ranged_weapon", family="shotgun", ammoFor="bullet"),
    )
    targets = [
        {
            "callId": "stats", "reason": "compiler_provenance_mismatched",
            "authoredParam": "ammoFor", "authoredValue": "empty",
            "compiledField": "ammoFor", "compiledValue": "bullet",
            "finalPath": "gameplay.ammoFor", "finalActual": "empty",
        },
        {
            "callId": "root", "reason": "compiler_provenance_mismatched",
            "authoredParam": "ammoFor", "authoredValue": "bullet",
            "compiledField": "ammoFor", "compiledValue": "bullet",
            "finalPath": "gameplay.ammoFor", "finalActual": "empty",
        },
    ]
    cards = author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"], targets, ENGINE_FUNCTION_CATALOG,
    )
    assert cards["stats"]["params"]["ammoFor"] == {"const": "bullet"}
    assert cards["root"]["params"]["ammoFor"] == {"const": "bullet"}
    assert cards["stats"]["requiredValues"] == {"ammoFor": "bullet"}
    assert cards["root"]["requiredValues"] == {"ammoFor": "bullet"}


def test_unknown_root_param_does_not_mask_pressure_repair_bounds() -> None:
    import json

    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request
    from infini_local.pipelines.combine_validation import _strict_authoring_validation

    current = _base_plan(
        "weapon",
        _call(
            "stats", "set_item_stats", resultKind="weapon", damageClass="magic",
            damage=22, useTimeTicks=17, useAnimationTicks=17, manaCost=7,
        ),
        _call(
            "root", "cast_magic_weapon", family="staff", projectileFamily="beam",
            movement="straight", speed=12, rangeTiles=80, lifetimeTicks=600,
            shotCount=1, spreadRadians=0, pierce=3, extraUpdates=2,
        ),
    )
    with __import__("pytest").raises(PlannerUnavailable) as captured:
        _strict_authoring_validation(current)
    targets = captured.value.author_repair_targets
    delete_target = next(
        target for target in targets
        if target.get("path") == "$.runtimePlan.engineCalls[1].params.extraUpdates"
        and target.get("kind") in {"runtime_validation", "additional_property"}
    )
    assert delete_target["callId"] == "root"
    root_pressure = next(target for target in targets if target.get("pressureEnvelope") and target.get("callId") == "root")
    stats_pressure = next(target for target in targets if target.get("pressureEnvelope") and target.get("callId") == "stats")
    assert root_pressure["repairParamConstraints"] == {
        "lifetimeTicks": {"maximum": 510},
        "shotCount": {"maximum": 1},
    }
    assert stats_pressure["repairParamConstraints"] == {
        "useTimeTicks": {"minimum": 20},
    }

    request, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, {"errors": targets}
    )
    assert targeted is True
    dossier = json.loads(user_content)
    assert dossier["repairFunctionCards"]["root"]["params"]["lifetimeTicks"]["maximum"] == 510
    assert dossier["repairFunctionCards"]["root"]["params"]["shotCount"]["maximum"] == 1
    assert dossier["repairFunctionCards"]["stats"]["params"]["useTimeTicks"]["minimum"] == 20
    response_schema = request["response_format"]["json_schema"]["schema"]
    patch_array = response_schema["properties"]["engineCallParamPatches"]
    branches = patch_array["items"]["anyOf"]
    root_branch = next(branch for branch in branches if branch["properties"]["callId"]["const"] == "root")
    stats_branch = next(branch for branch in branches if branch["properties"]["callId"]["const"] == "stats")
    assert root_branch["properties"]["params"]["properties"]["lifetimeTicks"]["maximum"] == 510
    assert stats_branch["properties"]["params"]["properties"]["useTimeTicks"]["minimum"] == 20


def test_control_derived_light_duration_does_not_create_false_dropped_receipt() -> None:
    from infini_local.core.runtime_authoring.final_projection import compile_runtime_plan_to_final_result

    tool = {
        "name": "Obsidian Pickaxe",
        "category": "tool",
        "concept": {"fantasy": "f", "mergeLogic": "m", "coreMechanic": "c"},
        "runtimeContract": {"primaryVerb": "mine", "controlStyle": "automatic"},
        "runtimePlan": {
            "resultKind": "tool",
            "engineCalls": [
                {"callId": "call_stats", "fn": "set_item_stats", "params": {
                    "resultKind": "tool", "damageClass": "melee", "damage": 15,
                    "useTimeTicks": 16, "useAnimationTicks": 20, "knockback": 3,
                    "maxStack": 1, "consumable": False,
                }},
                {"callId": "call_tool", "fn": "tool_capability", "params": {
                    "pickPower": 110, "axePower": 0, "hammerPower": 0,
                    "miningSpeedScale": 1.1,
                }},
                {"callId": "call_light", "fn": "emit_light", "params": {
                    "strength": 0.3, "color": "orange", "durationTicks": 10,
                }},
            ],
        },
    }
    result = compile_runtime_plan_to_final_result(tool)
    assert result["finalSections"]["gameplay"]["holdLightStrength"] == 0.3
    assert result["finalSections"]["gameplay"]["holdLightColorName"] == "orange"
    assert not any(
        row.get("callId") == "call_light"
        and row.get("authoredParam") == "durationTicks"
        and row.get("status") == "dropped"
        for row in result["finalWireReceipts"]
    )

    combat = deepcopy(tool)
    combat["category"] = "weapon"
    combat["runtimePlan"] = {
        "resultKind": "weapon",
        "engineCalls": [
            {"callId": "call_stats", "fn": "set_item_stats", "params": {
                "resultKind": "weapon", "damageClass": "ranged", "damage": 12,
                "useTimeTicks": 20, "useAnimationTicks": 20,
                "maxStack": 1, "consumable": False,
            }},
            {"callId": "call_shot", "fn": "shoot_projectile", "params": {
                "runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight",
                "speed": 8, "rangeTiles": 30, "lifetimeTicks": 90,
                "shotCount": 1, "spreadRadians": 0, "pierce": 1,
            }},
            {"callId": "call_light", "fn": "emit_light", "params": {
                "strength": 0.7, "color": "blue", "durationTicks": 41,
            }},
        ],
    }
    combat_result = compile_runtime_plan_to_final_result(combat)
    assert combat_result["finalSections"]["attack"]["runtimeLightDurationTicks"] == 41


def test_strict_author_preflight_surfaces_latent_projectile_pressure() -> None:
    import json

    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request
    from infini_local.pipelines.combine_validation import _strict_authoring_validation

    current = _base_plan(
        "weapon",
        _call(
            "stats", "set_item_stats", resultKind="weapon", damage=18,
            useTimeTicks=25, useAnimationTicks=25, maxStack=1, consumable=False,
        ),
        _call(
            "root", "shoot_projectile", runtimeFamily="yoyo", delivery="swing",
            movement="yoyo_hover", speed=16, rangeTiles=15, lifetimeTicks=900,
            pierce=-1, shotCount=1, spreadRadians=0,
        ),
    )
    current["name"] = "Demonite Yoyo"
    with __import__("pytest").raises(PlannerUnavailable) as captured:
        _strict_authoring_validation(current)
    targets = captured.value.author_repair_targets
    pressure_targets = [target for target in targets if target.get("pressureEnvelope")]
    assert {target["callId"] for target in pressure_targets} == {"stats", "root"}
    root_target = next(target for target in pressure_targets if target["callId"] == "root")
    stats_target = next(target for target in pressure_targets if target["callId"] == "stats")
    assert root_target["repairParamNames"] == ["shotCount", "lifetimeTicks"]
    assert stats_target["repairParamNames"] == ["useTimeTicks"]
    assert root_target["pressureEnvelope"]["metrics"]["activeProjectileEstimate"] == 36.0

    request, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, {"errors": targets}
    )
    assert targeted is True
    dossier = json.loads(user_content)
    root_card_params = set(dossier["repairFunctionCards"]["root"]["params"])
    assert {"shotCount", "lifetimeTicks"}.issubset(root_card_params)
    assert "extraUpdates" not in root_card_params
    response_schema = request["response_format"]["json_schema"]["schema"]
    patch_property = response_schema["properties"]["engineCallParamPatches"]
    patch_array = patch_property
    assert patch_array["type"] == "array"
    patch_branches = patch_array["items"]["anyOf"]
    root_branch = next(
        branch
        for branch in patch_branches
        if branch["properties"]["callId"]["const"] == "root"
    )
    params_schema = root_branch["properties"]["params"]
    params_object = next(
        branch for branch in params_schema["anyOf"] if branch.get("type") == "object"
    )
    root_schema_params = set(params_object["properties"])
    assert {"shotCount", "lifetimeTicks"}.issubset(root_schema_params)
    assert "extraUpdates" not in root_schema_params

    current["runtimePlan"]["engineCalls"][1]["params"]["extraUpdates"] = 1
    with __import__("pytest").raises(PlannerUnavailable) as authored_extra:
        _strict_authoring_validation(current)
    authored_extra_root = next(
        target
        for target in authored_extra.value.author_repair_targets
        if target.get("callId") == "root" and target.get("pressureEnvelope")
    )
    assert authored_extra_root["repairParamNames"] == [
        "shotCount", "extraUpdates", "lifetimeTicks",
    ]


def test_union_branch_diagnostic_authorizes_the_real_numeric_leaf() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import ENGINE_FUNCTION_CATALOG
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="melee", damage=14, knockback="3"),
        _call("root", "shoot_projectile", runtimeFamily="throw", delivery="throw", movement="gravity_arc"),
    )
    failure = {"runtimeValidation": {"errorDetails": [{
        "path": "$.runtimePlan.engineCalls[0].params.knockback.int",
        "callId": "stats", "fn": "set_item_stats",
        "reason": "Input should be a valid integer",
    }]}}
    cards = author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"], author_item_repair_scope._repair_targets(failure),
        ENGINE_FUNCTION_CATALOG,
    )
    assert cards["stats"]["requiredParamPaths"] == ["knockback"]
    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current,
        {"engineCallParamPatches": [{
            "callId": "stats", "fn": "set_item_stats", "params": {"knockback": 3},
        }]},
        failure,
    )
    assert repaired["runtimePlan"]["engineCalls"][0]["params"]["knockback"] == 3


def test_overhead_barrage_required_children_are_typed_repair_leaves() -> None:
    from infini_local.core.runtime_authoring.function_contract_registry import ENGINE_FUNCTION_CATALOG
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="magic", damage=45),
        _call(
            "barrage", "shoot_projectile", runtimeFamily="overhead_barrage",
            delivery="shoot", movement="gravity_arc", delayTicks=10,
        ),
    )
    failure = {"runtimeValidation": {"errorDetails": [
        {
            "path": "$.runtimePlan.engineCalls[1].params.secondaryDamageMultiplier",
            "callId": "barrage", "fn": "shoot_projectile",
            "reason": "requires explicit secondaryDamageMultiplier",
        },
        {
            "path": "$.runtimePlan.engineCalls[1].params.secondaryLifetimeTicks",
            "callId": "barrage", "fn": "shoot_projectile",
            "reason": "requires explicit secondaryLifetimeTicks",
        },
    ]}}
    cards = author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"], author_item_repair_scope._repair_targets(failure),
        ENGINE_FUNCTION_CATALOG,
    )
    assert set(cards["barrage"]["requiredParamPaths"]) == {
        "secondaryDamageMultiplier", "secondaryLifetimeTicks",
    }
    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current,
        {"engineCallParamPatches": [{
            "callId": "barrage", "fn": "shoot_projectile",
            "params": {
                "secondaryDamageMultiplier": 0.5,
                "secondaryLifetimeTicks": 60,
            },
        }]},
        failure,
    )
    params = repaired["runtimePlan"]["engineCalls"][1]["params"]
    assert params["secondaryDamageMultiplier"] == 0.5
    assert params["secondaryLifetimeTicks"] == 60


def test_alt_mobility_repair_requires_mode_and_mobility_mode_pair() -> None:
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.core.runtime_authoring.function_contract_registry import ENGINE_FUNCTION_CATALOG
    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="magic", damage=45),
        _call("root", "shoot_projectile", runtimeFamily="shoot", delivery="shoot", movement="straight"),
        _call("alt", "set_alt_use_mode", mode="recall_home", cooldownTicks=1800),
    )
    failure = {"runtimeValidation": {"errorDetails": [{
        "path": "$.runtimePlan.engineCalls[2].params.mode",
        "callId": "alt", "fn": "set_alt_use_mode", "reason": "unsupported mode=recall_home",
    }]}}
    targets = author_item_repair_scope._repair_targets(failure)
    cards = author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"], targets, ENGINE_FUNCTION_CATALOG,
    )
    assert cards["alt"]["requiredTogether"] == [["mobilityMode", "mode"]]
    assert cards["alt"]["allowedTogetherValues"] == [{
        "mode": "mobility", "mobilityMode": "recall_home",
    }]
    with __import__("pytest").raises(PlannerUnavailable, match="incomplete_dependency_group"):
        author_item_repair_delta._apply_targeted_repair_delta(
            current,
            {"engineCallParamPatches": [{
                "callId": "alt", "fn": "set_alt_use_mode", "params": {"mode": "mobility"},
            }]},
            failure,
        )
    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current,
        {"engineCallParamPatches": [{
            "callId": "alt", "fn": "set_alt_use_mode",
            "params": {"mode": "mobility", "mobilityMode": "recall_home"},
        }]},
        failure,
    )
    assert repaired["runtimePlan"]["engineCalls"][2]["params"]["mobilityMode"] == "recall_home"


def test_dropped_provenance_routes_to_exact_param_delete_delta() -> None:
    import json

    from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    llm_authoring_pipeline,
)

    current = _base_plan(
        "potion",
        _call(
            "stats", "set_item_stats", resultKind="potion", healLife=150,
            armorSlot="none", defense=0, consumable=True, maxStack=9999,
        ),
        _call("effect", "apply_player_effect_on_use", healLife=150),
    )
    current.update({
        "name": "Glowing Potion",
        "concept": {"fantasy": "f", "mergeLogic": "m", "coreMechanic": "c"},
        "runtimeContract": {"primaryVerb": "consume", "controlStyle": "tap"},
    })
    failure = {"authorRepairTargets": [
        {"callId": "stats", "fn": "set_item_stats", "reason": "compiler_provenance_dropped", "authoredParam": "armorSlot"},
        {"callId": "stats", "fn": "set_item_stats", "reason": "compiler_provenance_dropped", "authoredParam": "defense"},
    ]}
    request, user_content, _, targeted, _ = author_item_repair.build_same_author_repair_request(
        current, {"name": "Healing Potion"}, {"name": "Glowing Mushroom"}, failure,
    )
    dossier = json.loads(user_content)
    assert targeted is True
    assert request["response_format"]["type"] == "json_schema"
    assert dossier["repairFunctionCards"] == {}
    assert dossier["paramDeleteSpecs"] == [{
        "callId": "stats", "fn": "set_item_stats", "paramPaths": ["armorSlot", "defense"],
    }]
    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current,
        {"engineCallParamDeletes": [{
            "callId": "stats", "fn": "set_item_stats", "paramPaths": ["armorSlot", "defense"],
        }]},
        failure,
    )
    params = repaired["runtimePlan"]["engineCalls"][0]["params"]
    assert "armorSlot" not in params
    assert "defense" not in params


def test_runtime_dump_tooltip_evidence_reaches_parent_card_without_interpretation() -> None:
    from pathlib import Path

    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm

    card = raw_parent_card_for_llm({
        "name": "Hermes Boots",
        "internalName": "HermesBoots",
        "sourceMod": "Terraria",
        "accessory": True,
        "tooltipLines": ["The wearer can run super fast", "5% increased movement speed"],
    })
    assert card["raw"]["item"]["tooltipLines"] == [
        "The wearer can run super fast",
        "5% increased movement speed",
    ]

    source = (
        Path(__file__).resolve().parents[2]
        / "ModSources/InfiniCrafterLocal/Common/Commands/InfiniDumpCommand.cs"
    ).read_text(encoding="utf-8")
    assert "tooltipLines = TryItemTooltipLines(item, type)" in source
    assert 'string key = "ItemTooltip." + TryItemName(type);' in source
    assert "raw = item.ModItem.Tooltip.Value;" in source


def test_csharp_item_vfx_transport_is_bounded_and_held_item_validated() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal"
    packet_ids = (root / "Common/InfiniNetPacketIds.cs").read_text(encoding="utf-8")
    mod_root = (root / "InfiniCrafterLocal.cs").read_text(encoding="utf-8")
    runtime = (root / "Common/VFX/InfiniItemVfxRuntime.cs").read_text(encoding="utf-8")
    model = (root / "Common/Models/GeneratedItemData.cs").read_text(encoding="utf-8")
    normalize = (root / "Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    item_runtime = (root / "Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    overlay = (root / "Common/Players/GeneratedEquipOverlayDrawLayer.cs").read_text(encoding="utf-8")

    assert "SyncGeneratedItemVfxEvent = 18" in packet_ids
    assert "InfiniItemVfxRuntime.HandleUseEventPacket(reader, whoAmI)" in mod_root
    assert "player.HeldItem?.ModItem is not" in runtime
    assert "!TryClaimServerUseEvent(player, generated.Data, alternateUse)" in runtime
    assert "Math.Clamp(player.HeldItem.useTime, 2, 60)" in runtime
    assert "ServerUseEventSeen[playerId]" in runtime
    assert "Main.netMode == NetmodeID.Server && !Main.dedServ" in runtime
    assert "relay.Send(-1, playerId)" in runtime
    assert "ClearUseEventCaches()" in runtime
    assert "MinimalItemEventManifest" in model
    assert '"while_held" or "while_equipped" =>' in model
    assert '"on_use" or "on_alt_use" =>' in model
    assert ".Where(IsExecutableItemVfxSlot)" in model
    assert '.OrderBy(slot => slot.Event is "on_use" or "on_alt_use" ? 0 : 1)' in model
    assert "clone.VfxManifest = itemEventManifest" in model
    for parent in ("Head", "Torso", "Leggings", "Wings"):
        assert f"AfterParent(PlayerDrawLayers.{parent})" in overlay
    assert "player.dye[dyeIndex].dye" in overlay
    assert "AssetSync?.EnsureAssetsForData(entry.Data)" in overlay
    assert "ResolveEquipPresentationData" in overlay
    assert "RequestOneFromServer(id, forceAssetRetry: true)" in overlay
    assert "GeneratedEquipmentPresentationPlayer" in overlay
    assert "OnVisibleEquipment(player, entry.Data)" in overlay
    assert 'OnLive(player, Data, "while_equipped")' not in item_runtime
    assert 'ConventionalAssetFileName(Id, "_equip_overlay")' in normalize
    assert '"pl:glow" => DustID.MagicMirror' in runtime


def test_vfx_batch_diversity_reports_exact_duplicate_signatures() -> None:
    def item(item_id: str, renderer: str, event: str = "travel") -> dict[str, object]:
        return {"id": item_id, "vfxManifest": {"slots": [{
            "event": event, "rendererKind": renderer, "channel": "motionTrail", "lane": "primary",
            "emissionMode": "wake", "particleSystemId": "pl:glow", "textureRole": "projectile", "particleRole": "child",
        }]}}

    homogeneous = [item(f"same-{i}", "historyRibbon") for i in range(5)]
    report = vfx_batch_diversity_report(homogeneous)
    assert report["ok"] is False
    assert report["largestDuplicateGroup"] == 5

    varied = [
        item("a", "historyRibbon"), item("b", "tipTrail"), item("c", "ghostArc"),
        item("d", "wavyStrip"), item("e", "orbitingMotes", "active"),
    ]
    report = vfx_batch_diversity_report(varied)
    assert report["ok"] is True, report


def test_placeable_only_parents_require_exact_executable_parent_tile() -> None:
    import json

    from infini_local.pipelines.combine_validation import _placeable_parent_role_report
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    extractinator = {
        "name": "Extractinator", "damage": -1, "consumable": True,
        "accessory": False, "headSlot": -1, "bodySlot": -1, "legSlot": -1,
        "createTile": 219, "createWall": -1, "placeStyle": 0,
    }
    silt = {
        "name": "Silt Block", "damage": -1, "consumable": True,
        "accessory": False, "headSlot": -1, "bodySlot": -1, "legSlot": -1,
        "createTile": 123, "createWall": -1, "placeStyle": 0,
    }
    invalid = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="ranged", damage=12, useTimeTicks=24, maxStack=1, craftYield=1, consumable=False),
        _call("root", "fire_ranged_weapon", family="gun", ammoFor="bullet", movement="straight", speed=10, rangeTiles=40, lifetimeTicks=80, shotCount=1, spreadRadians=0, pierce=1),
    )
    report = _placeable_parent_role_report(invalid, extractinator, silt)
    assert report["ok"] is False
    target = {
        "path": "$.runtimePlan.engineCalls",
        "kind": "placeable_parent_unrepresentable_mechanic",
        "reason": "unrepresentable_mechanic: placeable-only parents require resultKind=furniture and placeable_behavior using an exact parent createTile/createWall id",
        "expectedResultKind": "furniture",
        "placeableParents": report["placeableParents"],
    }
    invalid.update({
        "name": "Silt Extractinator",
        "concept": {"fantasy": "f", "mergeLogic": "m", "coreMechanic": "c"},
        "runtimeContract": {"primaryVerb": "place", "controlStyle": "tap"},
    })
    _, user_content, _, targeted, _ = build_same_author_repair_request(
        invalid, extractinator, silt, {"authorRepairTargets": [target]},
    )
    assert targeted is False
    repair_payload = json.loads(user_content)
    assert repair_payload["repairMode"] == "full_redesign"
    assert repair_payload["mandatoryRedesignContracts"] == [{
        "category": "furniture",
        "resultKind": "furniture",
        "requiredEngineFunction": "placeable_behavior",
        "exactParentPlacementCandidates": report["placeableParents"],
        "furnitureStats": {"consumable": True, "maxStack": ">1"},
    }]

    valid = _base_plan(
        "furniture",
        _call("stats", "set_item_stats", resultKind="furniture", damageClass="generic", damage=0, useTimeTicks=15, useAnimationTicks=15, maxStack=99, craftYield=1, consumable=True),
        _call("place", "placeable_behavior", createTile=219, createWall=-1, placeStyle=0),
    )
    assert runtime_plan_validation_report(deepcopy(valid))["ok"] is True
    patch = compile_runtime_plan_to_genome_patch(deepcopy(valid))
    assert (patch["createTile"], patch["createWall"], patch["placeStyle"]) == (219, -1, 0)
    from infini_local.core.runtime_authoring.final_projection import compile_runtime_plan_to_final_result
    projected = compile_runtime_plan_to_final_result(deepcopy(valid))["finalSections"]
    assert (
        projected["gameplay"]["createTile"],
        projected["gameplay"]["createWall"],
        projected["gameplay"]["placeStyle"],
    ) == (219, -1, 0)

    from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
    from infini_local.core.runtime_contracts import structural_final_wire_report

    wired = attach_gameplay_and_attack(deepcopy(valid), extractinator, silt, {}, {})
    assert (
        wired["gameplay"]["createTile"],
        wired["gameplay"]["createWall"],
        wired["gameplay"]["placeStyle"],
    ) == (219, -1, 0)
    placement_receipts = [
        row for row in wired["runtimeContract"]["finalWireReceipts"]
        if row.get("callId") == "place"
    ]
    assert {
        (row["authoredParam"], row["finalPath"], row["status"])
        for row in placement_receipts
    } == {
        ("createTile", "gameplay.createTile", "active"),
        ("createWall", "gameplay.createWall", "active"),
        ("placeStyle", "gameplay.placeStyle", "active"),
    }
    assert structural_final_wire_report(wired)["ok"] is True
    assert _placeable_parent_role_report(valid, extractinator, silt)["ok"] is True


def test_visual_role_contracts_preserve_authored_geometry_and_split_sentry_roles() -> None:
    from infini_local.pipelines.visual_asset_plan import visual_asset_runtime_gate
    from infini_local.pipelines.visual_director_contract import (
        visual_director_context,
        visual_kit_projection_errors,
    )
    from infini_local.pipelines.visual_prompt_contracts import (
        sprite_contract_for,
        zimage_positive_guard_clause,
        zimage_role_description,
    )

    projectile_guard = zimage_positive_guard_clause("projectile", {})
    assert "without adding beam" not in projectile_guard
    assert "explicitly authored projectile body, beam, tether, and trail" in projectile_guard

    assert "wearable equipment overlay" in zimage_role_description("equip_overlay", 48)
    overlay_guard = zimage_positive_guard_clause("equip_overlay", {})
    assert "not an inventory icon or armor sheet" in overlay_guard
    overlay_contract = sprite_contract_for("equip_overlay", 48)
    assert overlay_contract["role"] == "equip_overlay"
    assert "player draw layer" in overlay_contract["promptPoseWords"]

    sentry = {
        "name": "Spider Sentry",
        "category": "weapon",
        "gameplay": {"kind": "weapon"},
        "attack": {
            "runtimeFamily": "sentry",
            "delivery": "summon",
            "projectileShape": "stationary spider turret body",
            "secondaryProjectileShape": "single venom fang shot",
        },
    }
    context = visual_director_context(sentry, {}, {})
    assert set(context["runtimeVisualRoleObligations"]) == {"projectile", "child"}
    incomplete = {
        "projectileSpritePrompt": "stationary spider turret body",
        "bakedAssets": {"projectile": {"mode": "baked_sprite", "distinctFromItem": True}},
    }
    errors = visual_kit_projection_errors(incomplete, sentry)
    assert any("sentry child required" in error for error in errors)
    complete = {
        **incomplete,
        "childSpritePrompt": "single venom fang shot",
        "bakedAssets": {
            **incomplete["bakedAssets"],
            "child": {"mode": "baked_sprite"},
        },
    }
    assert not [error for error in visual_kit_projection_errors(complete, sentry) if error.startswith("sentry ")]
    assert visual_asset_runtime_gate(sentry, "child", "baked_sprite") == ("baked_sprite", "")

    summon = deepcopy(sentry)
    summon["attack"] = {
        "enabled": True,
        "runtimeFamily": "summon",
        "delivery": "summon",
        "projectileShape": "bird",
        "projectileMotion": "float",
    }
    summon_context = visual_director_context(summon, {}, {})
    assert set(summon_context["runtimeVisualRoleObligations"]) == {"projectile"}
    summon_kit = {
        "projectileSpritePrompt": "single optical finch minion body",
        "bakedAssets": {},
    }
    assert visual_kit_projection_errors(summon_kit, summon) == [
        "summon projectile body required: baked_sprite + projectileSpritePrompt or reuse_item_sprite"
    ]
    summon_kit["bakedAssets"]["projectile"] = {"mode": "particle_vfx"}
    assert visual_kit_projection_errors(summon_kit, summon) == [
        "summon projectile body required: baked_sprite + projectileSpritePrompt or reuse_item_sprite"
    ]
    summon_kit["bakedAssets"]["projectile"] = {"mode": "baked_sprite"}
    assert visual_kit_projection_errors(summon_kit, summon) == []
    summon_kit["bakedAssets"]["projectile"] = {"mode": "reuse_item_sprite"}
    summon_kit["projectileSpritePrompt"] = ""
    assert visual_kit_projection_errors(summon_kit, summon) == []


def test_placeable_behavior_crosses_generated_item_csharp_boundary() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal/Common/Models"
    model = (root / "GeneratedItemData.Model.cs").read_text(encoding="utf-8")
    normalize = (root / "GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    apply = (root / "GeneratedItemData.Apply.cs").read_text(encoding="utf-8")

    for field, default in (("CreateTile", "-1"), ("CreateWall", "-1"), ("PlaceStyle", "0")):
        assert f"public int {field} {{ get; set; }} = {default};" in model
    assert "Gameplay.CreateTile < TileLoader.TileCount" in normalize
    assert "Gameplay.CreateWall < WallLoader.WallCount" in normalize
    assert "item.createTile = Gameplay.CreateTile;" in apply
    assert "item.createWall = Gameplay.CreateWall;" in apply
    assert "item.placeStyle = Math.Max(0, Gameplay.PlaceStyle);" in apply
    assert "item.consumable = true;" in apply


def test_placeable_role_yields_to_typed_potion_parent_and_rejects_dual_use_call() -> None:
    import json

    from infini_local.pipelines.combine_validation import (
        _parent_role_preservation_report,
        _placeable_parent_role_report,
    )
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    potion = {
        "name": "Healing Potion", "damage": -1, "healLife": 100,
        "accessory": False, "headSlot": -1, "bodySlot": -1, "legSlot": -1,
        "createTile": -1, "createWall": -1,
    }
    mushroom = {
        "name": "Glowing Mushroom", "damage": -1, "healLife": 0,
        "accessory": False, "headSlot": -1, "bodySlot": -1, "legSlot": -1,
        "createTile": 190, "createWall": -1, "placeStyle": 0,
    }
    plan = _base_plan(
        "potion",
        _call("stats", "set_item_stats", resultKind="potion", damageClass="generic", damage=0, useTimeTicks=17, useAnimationTicks=17, maxStack=99, craftYield=1, consumable=True, healLife=100),
        _call("use", "apply_player_effect_on_use", healLife=100),
        _call("place", "placeable_behavior", createTile=190, createWall=-1, placeStyle=0),
    )
    role = _placeable_parent_role_report(plan, potion, mushroom)
    assert role == {"ok": True, "applicable": False, "parentStrongRoles": ["potion"]}
    assert _parent_role_preservation_report(plan, potion, mushroom) == {
        "ok": True,
        "applicable": True,
        "parentStrongRoles": ["potion"],
        "expectedResultKind": "potion",
        "actualResultKind": "potion",
    }
    furniture = deepcopy(plan)
    furniture["category"] = "furniture"
    furniture["runtimePlan"]["resultKind"] = "furniture"
    furniture["runtimePlan"]["engineCalls"][0]["params"]["resultKind"] = "furniture"
    drift = _parent_role_preservation_report(furniture, potion, mushroom)
    assert drift["ok"] is False
    assert drift["expectedResultKind"] == "potion"

    failure = {"authorRepairTargets": [{
        "path": "$.runtimePlan.engineCalls[2]",
        "callId": "place",
        "fn": "placeable_behavior",
        "kind": "structural_call_rejected",
        "reason": "placeable_behavior requires resultKind=furniture, got potion",
    }]}
    _, repair_user_content, _, targeted, _ = build_same_author_repair_request(
        plan, potion, mushroom, failure,
    )
    dossier = json.loads(repair_user_content)
    assert targeted is False
    assert dossier["mandatoryRedesignContracts"] == [{
        "category": "potion",
        "resultKind": "potion",
        "requiredEngineFunction": "apply_player_effect_on_use",
        "rawParentStrongRole": "potion",
    }]

    report = runtime_plan_validation_report(plan)
    assert report["ok"] is False
    assert any(
        detail.get("kind") == "structural_call_rejected"
        and detail.get("callId") == "place"
        for detail in report["errorDetails"]
    )


def test_equipment_exclusivity_and_autoreuse_fail_before_final_provenance() -> None:
    accessory = _base_plan(
        "accessory",
        _call("stats", "set_item_stats", resultKind="accessory", damageClass="generic", damage=0, useTimeTicks=0, useAnimationTicks=0, maxStack=1, craftYield=1, consumable=False, autoReuse=True),
        _call("accessory", "accessory_effect", archetype="mobility", stats={"movementSpeed": 0.1}),
        _call("armor", "armor_effect", armorSlot="legs", archetype="mobility", defense=0, stats={"movementSpeed": 0.1}),
    )
    report = runtime_plan_validation_report(accessory)
    assert report["ok"] is False
    assert any(
        detail.get("kind") == "structural_call_rejected"
        and detail.get("callId") == "armor"
        for detail in report["errorDetails"]
    )
    auto = next(
        detail for detail in report["errorDetails"]
        if detail.get("callId") == "stats" and detail.get("repairParamNames") == ["autoReuse"]
    )
    assert "autoReuse=false" in auto["reason"]

    utility_armor = _base_plan(
        "armor",
        _call("stats", "set_item_stats", resultKind="armor", damageClass="generic", damage=0, useTimeTicks=0, useAnimationTicks=0, armorSlot="head", defense=2, maxStack=1, craftYield=1, consumable=False, autoReuse=False),
        _call("armor", "armor_effect", armorSlot="head", archetype="utility", defense=2, stats={"lightStrength": 1.0, "lightColorName": "yellow", "attackSpeed": 0.1}),
    )
    utility_report = runtime_plan_validation_report(deepcopy(utility_armor))
    assert utility_report["ok"] is True, utility_report
    utility_patch = compile_runtime_plan_to_genome_patch(deepcopy(utility_armor))
    assert utility_patch["armor"]["archetype"] == "utility"
    assert utility_patch["armor"]["lightStrength"] == 1.0
    assert utility_patch["armor"]["lightColorName"] == "yellow"
    assert utility_patch["armor"]["attackSpeed"] == 0.1


def test_repair_schema_without_runtime_plan_and_delete_patch_do_not_conflict() -> None:
    from infini_local.pipelines.author_item_contract import author_item_provider_repair_response_schema
    from infini_local.pipelines.author_item_repair_scope import (
        _targeted_repair_param_paths,
        _targeted_required_param_paths,
    )

    schema = author_item_provider_repair_response_schema({"visualIntent"})
    assert set(schema["properties"]) == {"visualIntent"}
    plan = {
        "engineCalls": [{
            "callId": "armor", "fn": "armor_effect",
            "params": {"setKey": "", "setBonus": "invalid"},
        }],
    }
    targets = [
        {"callId": "armor", "fn": "armor_effect", "path": "$.runtimePlan.engineCalls[0].params.setBonus", "reason": "invalid set bonus"},
        {"callId": "armor", "reason": "compiler_provenance_dropped", "authoredParam": "setBonus"},
        {"callId": "armor", "reason": "compiler_provenance_dropped", "authoredParam": "setKey"},
    ]
    assert _targeted_repair_param_paths(plan, targets) == {}
    assert _targeted_required_param_paths(plan, targets) == {}


def test_initial_prompt_exposes_placeable_only_obligation_but_not_incidental_material() -> None:
    from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload

    extractinator = {"name": "Extractor", "damage": -1, "createTile": 219, "createWall": -1, "headSlot": -1, "bodySlot": -1, "legSlot": -1}
    silt = {"name": "Silt", "damage": -1, "createTile": 123, "createWall": -1, "headSlot": -1, "bodySlot": -1, "legSlot": -1}
    payload = build_llm_author_payload(extractinator, silt, {}, {}, "placeable")
    obligation = payload["engineRuntimeContract"]["sourceDerivedParentRoleObligation"]
    assert obligation["expectedResultKind"] == "furniture"
    assert obligation["requiredEngineFunction"] == "placeable_behavior"

    potion = {"name": "Potion", "damage": -1, "healLife": 100, "createTile": -1, "createWall": -1, "headSlot": -1, "bodySlot": -1, "legSlot": -1}
    mushroom = {"name": "Mushroom", "damage": -1, "createTile": 190, "createWall": -1, "headSlot": -1, "bodySlot": -1, "legSlot": -1}
    payload = build_llm_author_payload(potion, mushroom, {}, {}, "potion")
    assert payload["engineRuntimeContract"]["sourceDerivedParentRoleObligation"] == {}


def test_hyphenated_unknown_param_keeps_exact_delete_path() -> None:
    import json

    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request
    from infini_local.pipelines.combine_validation import _strict_authoring_validation

    current = _base_plan(
        "weapon",
        _call(
            "stats", "set_item_stats", resultKind="weapon", damageClass="magic",
            damage=22, useTimeTicks=17, useAnimationTicks=17, maxStack=1,
            craftYield=1, consumable=False, rarity=1,
        ),
        _call(
            "root", "shoot_projectile", delivery="shoot", runtimeFamily="shoot",
            movement="straight", speed=11, rangeTiles=60, lifetimeTicks=600,
            shotCount=1, spreadRadians=0, pierce=3,
        ),
    )
    current["runtimePlan"]["engineCalls"][0]["params"]["rar-1"] = 1
    with __import__("pytest").raises(PlannerUnavailable) as captured:
        _strict_authoring_validation(current)

    _, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, {"errors": captured.value.author_repair_targets}
    )
    assert targeted is True
    dossier = json.loads(user_content)
    stats_delete = next(
        spec for spec in dossier["paramDeleteSpecs"] if spec["callId"] == "stats"
    )
    assert stats_delete["paramPaths"] == ["rar-1"]


def test_cast_magic_beam_uses_direct_beam_charge_field_without_alias() -> None:
    from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
    from infini_local.core.runtime_authoring.semantics import _lower_typed_engine_call

    params = {
        "family": "channelled_beam",
        "projectileFamily": "beam",
        "beamWidthPx": 12,
        "beamChargeTicks": 0,
        "immunityCooldown": 15,
    }
    parsed = engine_params_model("cast_magic_weapon").model_validate(params)
    lowered = _lower_typed_engine_call(
        "cast_magic_weapon", parsed.model_dump(exclude_none=True)
    )
    assert lowered[0][1]["beamChargeTicks"] == 0
    assert "chargeTicks" not in lowered[0][1]


def test_object_param_patch_authorizes_exact_subtree_and_required_parent() -> None:
    from infini_local.pipelines.author_item_repair_delta import _apply_targeted_repair_delta

    current = _base_plan(
        "armor",
        _call(
            "stats", "set_item_stats", resultKind="armor", damageClass="generic",
            damage=0, useTimeTicks=10, useAnimationTicks=10, armorSlot="head",
            defense=2, maxStack=1, craftYield=1, consumable=False,
        ),
        _call(
            "armor", "armor_effect", armorSlot="head", setKey="",
            archetype="utility", defense=2,
            stats={"lightStrength": 1.0, "lightColorName": "orange"},
            setBonus="",
        ),
    )
    failure = {"errors": [{
        "path": "$.runtimePlan.engineCalls[1].params.setBonus",
        "callId": "armor",
        "fn": "armor_effect",
        "kind": "runtime_validation",
        "reason": "setBonus must be an object",
        "repairParamNames": ["setBonus"],
    }]}
    repaired = _apply_targeted_repair_delta(
        current,
        {"engineCallParamPatches": [{
            "callId": "armor",
            "fn": "armor_effect",
            "params": {"setBonus": {"text": ""}},
        }]},
        failure,
    )
    armor = repaired["runtimePlan"]["engineCalls"][1]["params"]
    assert armor["setBonus"] == {"text": ""}


def test_blank_optional_authored_values_do_not_claim_final_wire_provenance() -> None:
    from infini_local.core.runtime_contracts import validate_structural_planner_contract

    data = {
        "runtimeContract": {
            "primaryVerb": "shoot",
            "controlStyle": "tap",
            "finalWireReceipts": [],
        },
        "runtimePlan": {
            "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {"ammoFor": ""}},
                {"callId": "hit", "fn": "apply_on_hit_effect", "params": {"debuffHint": None}},
            ],
        },
    }
    report = validate_structural_planner_contract(data)
    missing = {
        (row.get("callId"), row.get("authoredParam"))
        for row in report["blockingClaims"]
        if row.get("kind") == "compiler_provenance_receipt_missing"
    }
    assert ("stats", "ammoFor") not in missing
    assert ("hit", "debuffHint") not in missing


def test_invalid_call_ids_plus_param_defect_use_one_atomic_strict_delta() -> None:
    import json

    from infini_local.pipelines.author_item_repair import build_same_author_repair_request
    from infini_local.pipelines.author_item_repair_delta import _apply_targeted_repair_delta

    current = _base_plan(
        "weapon",
        _call("1", "set_item_stats", resultKind="weapon", damageClass="summon", damage=18, useTimeTicks=30),
        _call("2", "deploy_sentry", family="spider", shotCount=1, spreadRadians=0, soundImpactCatalogId="bad_sound"),
        _call("3", "apply_on_hit_effect", onHit="poison", count=0, chainCount=0, aoeRadiusTiles=0, secondaryDamageMultiplier=0, secondaryLifetimeTicks=5, pullStrength=0, pullMode="none", debuffHint="venom", debuffTime=120),
    )
    failure = {"errors": [
        {
            "path": "$.runtimePlan.engineCalls[1].params.soundImpactCatalogId",
            "callId": "2",
            "fn": "deploy_sentry",
            "kind": "runtime_validation",
            "repairParamNames": ["soundImpactCatalogId"],
            "reason": "invalid sound catalog id",
        },
        *[
            {
                "path": f"$.runtimePlan.engineCalls[{index}].callId",
                "callId": str(index + 1),
                "fn": call["fn"],
                "kind": "invalid_or_missing_call_id",
                "reason": "invalid_or_missing_call_id",
            }
            for index, call in enumerate(current["runtimePlan"]["engineCalls"])
        ],
    ]}
    request, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, failure
    )
    assert targeted is True
    dossier = json.loads(user_content)
    assert dossier["repairMode"] == "targeted_leaf_delta"
    assert len(dossier["targetedRepairDeltaShape"]["engineCallIdPatches"]) == 1
    assert "engineCallParamPatches" in dossier["targetedRepairDeltaShape"]
    schema = request["response_format"]["json_schema"]["schema"]
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"engineCallParamPatches", "engineCallIdPatches"}
    assert schema["properties"]["engineCallIdPatches"]["minItems"] == 3
    assert schema["properties"]["engineCallIdPatches"]["maxItems"] == 3

    repaired = _apply_targeted_repair_delta(current, {
        "engineCallParamPatches": [{
            "callId": "beam_shot",
            "fn": "deploy_sentry",
            "params": {"soundImpactCatalogId": "impact_creature_meow"},
        }],
        "engineCallIdPatches": [
            {"callIndex": 0, "currentCallId": "1", "fn": "set_item_stats", "newCallId": "item_stats"},
            {"callIndex": 1, "currentCallId": "2", "fn": "deploy_sentry", "newCallId": "beam_shot"},
            {"callIndex": 2, "currentCallId": "3", "fn": "apply_on_hit_effect", "newCallId": "poison_hit"},
        ],
    }, failure)
    repaired_calls = repaired["runtimePlan"]["engineCalls"]
    assert [call["callId"] for call in repaired_calls] == ["item_stats", "beam_shot", "poison_hit"]
    assert repaired_calls[1]["params"]["soundImpactCatalogId"] == "impact_creature_meow"


def test_unknown_nested_author_property_routes_to_full_redesign() -> None:
    import json

    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="magic", damage=20, useTimeTicks=20),
        _call("root", "cast_magic_weapon", family="staff", projectileFamily="bolt", movement="straight", speed=10, rangeTiles=40, lifetimeTicks=90, shotCount=1, spreadRadians=0, pierce=1, extraUpdates=2),
    )
    current["runtimePlan"]["visualIntent"]["item:"] = "typo"
    failure = {"errors": [
        {
            "path": "$.runtimePlan.engineCalls[1].params.extraUpdates",
            "callId": "root",
            "fn": "cast_magic_weapon",
            "kind": "additional_property",
            "reason": "Extra inputs are not permitted",
        },
        {
            "path": "$.runtimePlan.visualIntent.item",
            "kind": "required",
            "reason": "required",
        },
        {
            "path": "$.runtimePlan.visualIntent.item:",
            "kind": "additional_property",
            "reason": "Extra inputs are not permitted",
        },
    ]}
    _, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, failure,
    )
    assert targeted is False
    assert json.loads(user_content)["repairMode"] == "full_redesign"


def test_held_yoyo_pressure_counts_one_runtime_root() -> None:
    from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch
    from infini_local.pipelines.engine_pressure_metrics import projectile_pressure_envelope_report

    current = _base_plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="weapon", damageClass="melee", damage=22, useTimeTicks=30),
        _call("root", "perform_melee_attack", family="yoyo", lifetimeTicks=1800, pierce=-1, rangeTiles=15, shotCount=1, speed=16, spreadRadians=0, useTimeTicks=25),
    )
    genome = compile_runtime_plan_to_genome_patch(current)
    report = projectile_pressure_envelope_report(genome, {})
    assert genome["runtimeFamily"] == "yoyo"
    assert report["metrics"]["activePrimaryProjectiles"] == 1.0
    assert report["ok"] is True


def test_particle_material_effect_error_is_atomic_targeted_repair() -> None:
    import json

    from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report
    from infini_local.pipelines.author_item_repair import build_same_author_repair_request

    current = _base_plan(
        "consumable_weapon",
        _call("stats", "set_item_stats", resultKind="consumable_weapon", damageClass="ranged", damage=20, useTimeTicks=30, consumable=True, maxStack=9999, craftYield=1),
        _call("root", "fire_ranged_weapon", family="dart", lifetimeTicks=120, movement="gravity_arc", pierce=1, rangeTiles=30, shotCount=1, speed=6, spreadRadians=0),
        _call("particles", "spawn_contact_particles", amount=10, durationTicks=15, effect="slime", material="slime", scale=1.0),
        _call("consume", "consumption_behavior", consumeChancePercent=100),
    )
    report = runtime_plan_validation_report(current)
    assert report["ok"] is False
    particle_targets = [
        row for row in report["errorDetails"]
        if row.get("callId") == "particles"
    ]
    assert {
        name for row in particle_targets for name in row.get("repairParamNames", [])
    } == {"effect", "material"}
    _, user_content, _, targeted, _ = build_same_author_repair_request(
        current, {}, {}, {"runtimeValidation": report},
    )
    dossier = json.loads(user_content)
    assert targeted is True
    assert {"effect", "material"}.issubset(
        set(dossier["repairFunctionCards"]["particles"]["params"])
    )
    combinations = dossier["repairFunctionCards"]["particles"]["allowedTogetherValues"]
    assert combinations
    assert all(
        row["material"] == "none" or row["effect"] in {"none", "dust"}
        for row in combinations
    )
