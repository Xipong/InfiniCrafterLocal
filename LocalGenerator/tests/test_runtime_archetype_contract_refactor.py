from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring import (
    compile_runtime_plan_to_genome_patch,
    compile_runtime_plan_to_genome_result,
)
from infini_local.core.runtime_archetypes import (
    boomerang_hit_estimate_from_patch,
    normalize_runtime_archetype,
)
from infini_local.core.runtime_contracts import normalize_runtime_contract
from infini_local.core.runtime_promise_truth import validate_runtime_promises
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload

ROOT = Path(__file__).resolve().parents[2]


def _stats_call() -> dict:
    return {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 18, "useTimeTicks": 28}}


def _shoot(**params) -> dict:
    base = {"runtimeFamily": "throw", "delivery": "throw", "movement": "straight", "speed": 8, "rangeTiles": 35, "lifetimeTicks": 90, "pierce": 0}
    base.update(params)
    return {"fn": "shoot_projectile", "params": base}


def test_runtime_archetype_normalizes_partial_bad_fields_and_preserves_unknown_knobs() -> None:
    spec = normalize_runtime_archetype({
        "source": "bogus",
        "family": "boomerang",
        "phaseModel": "wrong",
        "overrideKnobs": {
            "returnDelayTicks": "999",
            "returnPierce": "-5",
            "beamWidthPx": "wide",
            "trailProfile": "amber_slime",
            "futureKnob": {"kept": True},
        },
    })

    assert spec["schema"] == "infini.runtime-archetype.v1"
    assert spec["source"] == "generated"
    assert spec["family"] == "boomerang"
    assert spec["phaseModel"] == "outbound_return"
    assert spec["overrideKnobs"]["returnDelayTicks"] == 180
    assert spec["overrideKnobs"]["returnPierce"] == -1
    assert spec["overrideKnobs"]["beamWidthPx"] == 18
    assert spec["overrideKnobs"]["trailProfile"] == "amber_slime"
    assert spec["overrideKnobs"]["futureKnob"] == {"kept": True}


def test_invalid_simple_runtime_archetype_family_with_executable_engine_calls_falls_back_to_custom_executor() -> None:
    data = {
        "runtimeArchetype": {"source": "generated", "family": "thrust"},
        "runtimeContract": {"primaryVerb": "thrusting melee hit"},
        "runtimePlan": {"engineCalls": [_stats_call(), _shoot(runtimeFamily="thrust", delivery="thrust", movement="straight")]},
    }

    result = compile_runtime_plan_to_genome_result(data)

    assert data["runtimeArchetype"]["family"] == "custom_executor"
    assert data["runtimeArchetype"]["supportStatus"] == "executable"
    assert result["compiled"]["archetypeCompiler"]["supportStatus"] == "executable"
    assert "unsupported_preserved_not_executed" not in result["compiled"]["archetypeCompiler"].get("warnings", [])
    assert "unsupported:unsupported" not in data.get("unsupportedPromises", [])


def test_old_recipe_without_runtime_archetype_compiles_unchanged_core_fields() -> None:
    data = {"runtimePlan": {"engineCalls": [_stats_call(), _shoot(runtimeFamily="shoot", delivery="shoot", movement="straight")]}}
    patch = compile_runtime_plan_to_genome_patch(data)

    assert "runtimeArchetype" not in data
    assert patch["runtimeFamily"] == "shoot"
    assert patch["delivery"] == "shoot"
    assert patch["movement"] == "straight"


def test_boomerang_archetype_maps_to_existing_returning_runtime_and_phase_metadata() -> None:
    data = {
        "runtimeArchetype": {"family": "boomerang", "overrideKnobs": {"returnPierce": -1, "outboundPierce": 1}},
        "runtimeContract": {"mechanicClaims": [{"claim": "returns to the thrower and can hit again on return", "backing": "runtimeArchetype.family=boomerang"}]},
        "runtimePlan": {"engineCalls": [_stats_call(), _shoot(runtimeFamily="throw", delivery="throw", movement="straight", pierce=0)]},
    }
    result = compile_runtime_plan_to_genome_result(data)
    patch = result["patch"]

    assert patch["runtimeFamily"] == "returning"
    assert patch["delivery"] == "throw"
    assert patch["movement"] == "boomerang"
    assert patch["weaponFamily"] == "boomerang"
    assert "weaponSubfamily" not in patch
    assert patch["archetypePhaseModel"] == "outbound_return"
    assert patch["returnPierce"] == -1
    assert result["compiled"]["runtimeArchetype"]["family"] == "boomerang"
    assert result["compiled"]["archetypeCompiler"]["supportStatus"] == "executable"


def test_yoyo_flail_whip_archetypes_map_only_to_existing_finite_runtime_families() -> None:
    cases = [
        ("yoyo", "yoyo", "yoyo", "yoyo_hover"),
        ("flail", "flail", "flail", "flail_tether"),
        ("whip", "whip", "whip", "whip_lash"),
    ]
    for family, runtime_family, delivery, movement in cases:
        data = {"runtimeArchetype": {"family": family}, "runtimePlan": {"engineCalls": [_stats_call(), _shoot(runtimeFamily="throw", delivery="throw", movement="straight")]}}
        patch = compile_runtime_plan_to_genome_patch(data)
        assert patch["runtimeFamily"] == runtime_family
        assert patch["delivery"] == delivery
        assert patch["movement"] == movement
        assert patch["archetypeCompiler"]["supportStatus"] == "executable"


def test_channel_beam_archetype_compiles_to_exact_held_executor_and_clamps_knobs() -> None:
    data = {
        "runtimeArchetype": {"family": "channel_beam", "overrideKnobs": {"chargeTicks": 500, "beamWidthPx": 900}},
        "runtimeContract": {"controlStyle": "hold-to-channel", "stateFields": ["chargeTicks"], "syncFields": ["owner", "beamRotation"]},
        "runtimePlan": {"engineCalls": [_stats_call()]},
    }
    result = compile_runtime_plan_to_genome_result(data)
    patch = result["patch"]

    assert patch["runtimeFamily"] == "beam"
    assert patch["movement"] == "phase"
    assert patch["channelUse"] is True
    assert patch["beamWidthPx"] == 96
    assert patch["beamChargeTicks"] == 300
    assert result["compiled"]["archetypeCompiler"]["supportStatus"] == "executable"
    assert result["compiled"]["runtimeArchetype"]["channelled"] is True
    assert result["compiled"]["runtimeArchetype"]["usesHeldProjectile"] is True
    assert not data.get("unsupportedPromises")


def test_runtime_contract_reports_only_unimplemented_sync_details_for_working_beam() -> None:
    data = {
        "runtimeArchetype": {"family": "channel_beam"},
        "runtimeContract": {"controlStyle": "hold-to-channel", "syncFields": ["owner", "phase", "beamRotation"]},
        "runtimePlan": {"engineCalls": [_stats_call()]},
    }
    result = compile_runtime_plan_to_genome_result(data)
    validation = result["validation"]

    assert not any("hold_to_channel" in warning for warning in validation["warnings"])
    assert validation["warnings"] == ["sync_contract_fields_not_active:phase"]
    assert result["runtimeContractValidation"]["executionStatus"] == "partial"
    assert data["unsupportedPromises"] == ["unsupported:sync:phase"]


def test_mechanic_claims_backed_by_archetype_are_executable_and_unbacked_claims_warn() -> None:
    backed = {
        "tooltip": "Returns to the thrower.",
        "runtimeArchetype": {"family": "boomerang"},
        "runtimeContract": {"mechanicClaims": [{"claim": "returns to the thrower", "backing": "runtimeArchetype.family=boomerang"}]},
        "runtimePlan": {"engineCalls": [_stats_call(), _shoot()]},
    }
    compile_runtime_plan_to_genome_result(backed)
    report = validate_runtime_promises(backed)
    assert report["claims"][0]["status"] == "executable"
    assert backed["runtimeContract"]["executionStatus"] == "executable"

    unbacked = {
        "tooltip": "Rains stars from the sky.",
        "concept": {"fantasy": "A sword that calls down starfall."},
        "runtimeContract": {"mechanicClaims": [{"claim": "rains stars from the sky", "backing": "unsupported"}]},
        "runtimePlan": {"engineCalls": [_stats_call(), _shoot(runtimeFamily="swing", delivery="swing", movement="straight")]},
    }
    compile_runtime_plan_to_genome_result(unbacked)
    report2 = validate_runtime_promises(unbacked)
    assert any(claim["kind"] == "overhead_barrage" and claim["status"] == "unsupported" for claim in report2["claims"])
    assert "unsupported:overhead_barrage" in unbacked.get("unsupportedPromises", [])

    backed_overhead_barrage = {
        "tooltip": "On hit, raining stars fall from the sky.",
        "runtimeContract": {"mechanicClaims": [{"claim": "raining stars fall on hit", "backing": "engineCall.apply_on_hit_effect"}]},
        "runtimePlan": {"engineCalls": [
            _stats_call(),
            _shoot(runtimeFamily="swing", delivery="swing", movement="straight"),
            {"fn": "apply_on_hit_effect", "params": {"onHit": "overhead_barrage", "count": 3}},
        ]},
    }
    result = compile_runtime_plan_to_genome_result(backed_overhead_barrage)
    assert result["patch"].get("onHit") == "overhead_barrage"
    report3 = validate_runtime_promises(backed_overhead_barrage, result["patch"])
    assert any(claim["kind"] == "overhead_barrage" and claim["status"] == "executable" for claim in report3["claims"])
    assert "unsupported:overhead_barrage" not in (backed_overhead_barrage.get("unsupportedPromises") or [])
    assert backed_overhead_barrage["runtimeContract"]["executionStatus"] == "executable"


def test_burst_claim_with_zero_burst_dust_cap_is_visible_as_partial_warning() -> None:
    data = {
        "tooltip": "Bursts on impact.",
        "runtimeContract": {"mechanicClaims": [{"claim": "bursts on hit", "backing": "engineCall.apply_on_hit_effect"}]},
        "runtimePlan": {"engineCalls": [_stats_call(), _shoot(runtimeFamily="shoot", delivery="shoot", movement="straight"), {"fn": "apply_on_hit_effect", "params": {"onHit": "burst"}}]},
    }
    result = compile_runtime_plan_to_genome_result(data)
    assert result["patch"].get("burstDustCap", 0) == 0
    report = validate_runtime_promises(data, result["patch"])
    assert any("burst_without_burstDustCap" in warning for warning in report["warnings"])


def test_boomerang_infinite_return_pierce_does_not_explode_baseline_dps_estimate() -> None:
    estimate = boomerang_hit_estimate_from_patch({"runtimeFamily": "returning", "pierce": -1, "returnPierce": -1, "archetypePhaseModel": "outbound_return"})

    assert estimate["baselineHits"] <= 3
    assert estimate["skillReturnHits"] <= 5
    assert estimate["scorerCapped"] is True


def test_prompt_builder_mentions_runtime_archetype_contract_without_item_name_tables() -> None:
    payload = build_llm_author_payload({"name": "Parent A"}, {"name": "Parent B"}, {}, {}, "a+b")
    text = json.dumps(payload, ensure_ascii=False)

    assert "runtimeArchetype" in text
    assert "runtimeContract" in text
    assert "mechanicClaims" in text
    assert "Engine still executes only registered finite primitives" in text
    for forbidden in ["Star Wrath", "Meowmere", "Terra Blade", "Last Prism"]:
        assert forbidden not in text


def test_visual_only_contract_does_not_route_gameplay_from_visual_text() -> None:
    data = {
        "visual": {"itemPrompt": "a sword emitting a huge beam aura"},
        "runtimeContract": {"mechanicClaims": [{"claim": "beam aura is visual only", "backing": "visual_only", "status": "visual_only"}]},
        "runtimePlan": {"engineCalls": [_stats_call(), _shoot(runtimeFamily="swing", delivery="swing", movement="straight")]},
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    report = validate_runtime_promises(data, patch)

    assert patch["runtimeFamily"] == "swing"
    assert patch["movement"] == "straight"
    assert all(claim.get("status") != "executable" for claim in report["claims"] if claim.get("kind") == "beam")


def test_runtime_archetype_contract_json_roundtrip_preserves_inert_unknowns() -> None:
    data = {
        "runtimeArchetype": normalize_runtime_archetype({"family": "boomerang", "overrideKnobs": {"futureKnob": {"nested": [1, 2]}}}),
        "runtimeContract": normalize_runtime_contract({"primaryVerb": "returning throw", "mechanicClaims": [{"claim": "returns", "backing": "runtimeArchetype.family=boomerang"}]}),
    }
    restored = json.loads(json.dumps(data, ensure_ascii=False))

    assert restored["runtimeArchetype"]["overrideKnobs"]["futureKnob"] == {"nested": [1, 2]}
    assert restored["runtimeContract"]["mechanicClaims"][0]["claim"] == "returns"


def test_csharp_generated_item_data_has_data_only_runtime_archetype_contract_surface() -> None:
    model = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs").read_text(encoding="utf-8")
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    serializer = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.cs").read_text(encoding="utf-8")

    assert "public RuntimeArchetypeSpec RuntimeArchetype { get; set; } = new();" in model
    assert "public RuntimeContractSpec RuntimeContract { get; set; } = new();" in model
    assert "public sealed class RuntimeArchetypeSpec" in model
    assert "public sealed class RuntimeContractSpec" in model
    assert "public sealed class MechanicClaimSpec" in model
    assert "RuntimeArchetype ??= new RuntimeArchetypeSpec();" in normalize
    assert "RuntimeContract ??= new RuntimeContractSpec();" in normalize
    assert "RuntimeArchetype.Normalize();" in normalize
    assert "RuntimeContract.Normalize();" in normalize
    assert "RuntimeArchetype" not in serializer[serializer.index("private sealed class PlayerSaveReferencePayload"):serializer.index("public string ToPlayerSaveJson")]


def test_projectile_bounce_is_not_false_feline_unsupported() -> None:
    data = {
        "tooltip": "Casts bouncy sparks that rebound from walls.",
        "runtimeContract": {"mechanicClaims": [{"claim": "Projectiles bounce on walls", "backing": "shoot_projectile:movement=bounce"}]},
        "runtimePlan": {"engineCalls": [
            _stats_call(),
            _shoot(runtimeFamily="cast", delivery="cast", movement="bounce"),
            {"fn": "apply_on_hit_effect", "params": {"onHit": "burn"}},
        ]},
    }
    result = compile_runtime_plan_to_genome_result(data)
    assert result["patch"].get("movement") == "bounce"
    report = validate_runtime_promises(data, result["patch"])
    kinds = {(c.get("kind"), c.get("status")) for c in report.get("claims") or []}
    assert ("projectile_bounce", "executable") in kinds
    assert not any(k == "feline_bounce" and st == "unsupported" for k, st in kinds)
    assert "unsupported:feline_bounce" not in (data.get("unsupportedPromises") or [])


def test_utility_engine_calls_override_unsupported_runtime_archetype_family() -> None:
    data = {
        "name": "Swift Boots",
        "category": "accessory",
        "runtimeArchetype": {"family": "unsupported"},
        "runtimePlan": {"engineCalls": [
            {"fn": "set_item_stats", "params": {"resultKind": "accessory", "rarity": 2}},
            {"fn": "accessory_effect", "params": {"archetype": "mobility", "movementSpeed": 0.15}},
        ]},
    }
    result = compile_runtime_plan_to_genome_result(data)
    assert data["runtimeArchetype"]["family"] == "custom_executor"
    assert data["runtimeArchetype"]["supportStatus"] == "executable"
    assert "unsupported:unsupported" not in (data.get("unsupportedPromises") or [])
    assert result["patch"].get("archetypeCompiler", {}).get("supportStatus") == "executable"


def test_emit_light_alone_does_not_make_unsupported_archetype_fully_executable() -> None:
    data = {
        "name": "Glow Relic",
        "category": "accessory",
        "runtimeArchetype": {"family": "unsupported"},
        "runtimePlan": {"engineCalls": [
            {"fn": "set_item_stats", "params": {"resultKind": "accessory", "rarity": 2}},
            {"fn": "emit_light", "params": {"strength": 0.55, "color": "blue"}},
        ]},
    }
    result = compile_runtime_plan_to_genome_result(data)
    assert data["runtimeArchetype"]["family"] == "unsupported"
    assert data["runtimeArchetype"]["supportStatus"] == "unsupported"
    assert "unsupported:unsupported" in (data.get("unsupportedPromises") or [])
    assert result["patch"].get("archetypeCompiler", {}).get("supportStatus") == "unsupported"


def test_set_item_stats_alone_does_not_override_unsupported_runtime_archetype_family() -> None:
    data = {
        "name": "Plain Trinket",
        "category": "accessory",
        "runtimeArchetype": {"family": "unsupported"},
        "runtimePlan": {"engineCalls": [
            {"fn": "set_item_stats", "params": {"resultKind": "accessory", "rarity": 1}},
        ]},
    }
    result = compile_runtime_plan_to_genome_result(data)
    assert data["runtimeArchetype"]["family"] == "unsupported"
    assert data["runtimeArchetype"]["supportStatus"] == "unsupported"
    assert "unsupported:unsupported" in (data.get("unsupportedPromises") or [])
    assert result["patch"].get("archetypeCompiler", {}).get("supportStatus") == "unsupported"
