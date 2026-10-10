"""The serialized Author packet exposes the canonical shape, units and construction grammar."""

from __future__ import annotations
from infini_local.core.runtime_authoring.capability_registry import visible_capabilities
import copy
import json
import re
from pathlib import Path
import pytest
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    INPUT_KIND_REGISTRY,
    EVENT_KIND_REGISTRY,
    compact_capability_catalog,
    validate_runtime_program,
)
from infini_local.core.runtime_authoring.capability_registry import runtime_authoring_prompt_field_guide
from infini_local.core.runtime_authoring.terraria_vocabulary import DAMAGE_CLASS_TOKENS
from infini_local.pipelines.author_item_contract import (
    author_item_response_schema,
    author_item_provider_response_schema,
    author_item_prompt_shape_card,
    author_item_repair_prompt_shape_card,
    author_item_repair_response_schema,
    primary_entity_llm_invariant,
    project_provider_author_item_to_local,
)
from infini_local.pipelines.llm_authoring_prompt import (
    PLANNER_PROMPT_LIMIT_CHARS,
    PLANNER_PROMPT_MIN_HEADROOM_CHARS,
    build_llm_author_payload,
    planner_prompt_usability_report,
    realization_execution_truth_for_llm,
)
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines import llm_authoring_pipeline as pipeline
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_author_request_compaction import _expand_constraint_references


@pytest.fixture
def packet(monkeypatch):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    a = {"name": "Thorn Whip", "fullName": "Terraria/ThornWhip", "damage": 7, "useTime": 20}
    b = {"name": "Workbench", "createTile": 18, "useTime": 15}
    request, user, system = build_initial_author_request(a, b, a, b, "whip+bench", model_name="test-model")
    assert request["response_format"] == {"type": "json_object"}
    assert [r["role"] for r in request["messages"]] == ["system", "user"]
    assert request["messages"][0]["content"] == system and request["messages"][1]["content"] == user
    return request, json.loads(user), system


def test_serialized_construction_is_one_immutable_response_without_draft_loop(packet):
    request, payload, system = packet
    assert not re.search(r"\b(verify|review|check)\b|before answering|before returning|reject the draft", system, re.I)
    assert "single immutable JSON object" in system and "double-quoted keys" in system
    assert "concept" in system and "selfEvaluation" in system and "diagnostic" in system.lower()
    assert "selfCheck" not in payload
    invariants = payload["runtimeProgramInvariants"]
    assert "structureCheck" not in invariants and "realizationExecutionTruth" not in invariants
    primary = invariants["primaryEntityOwnership"]
    assert primary["authoredField"] == "runtimeProgram.primaryEntityId" and primary["exactlyOnePrimaryEntity"] is True
    assert "do not carry role" in primary["primaryRule"]
    assert "preEmissionCheck" not in primary_entity_llm_invariant()
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    assert "requiredComponents" in catalog["entityKinds"][0]
    assert {"paramNotation", "referenceRules"} <= catalog["fieldGuide"].keys()
    assert "on_use" in {r["event"] for r in catalog["events"]}
    assert "charge_then_release" in {r["fn"] for r in catalog["capabilities"]}
    assert "selfEvaluation" in payload["diagnosticReport"]
    user = request["messages"][1]["content"]
    for phrase in ("Before answering", "Check each", "Walk every", "draft-reject", "second design pass"):
        assert phrase.lower() not in user.lower()
    assert "concept" in user and "realization" in user
    expected = {r["fn"]: r for r in compact_capability_catalog()}
    assert _expand_constraint_references(
        {r["fn"]: {k: v for k, v in r.items() if k != "constructionMeaning"}
         for r in catalog["capabilities"]}, catalog["fieldGuide"]["consumerConstraints"]) == expected
    assert set(expected) == {cap.name for cap in visible_capabilities()}
    assert sum(len(r["params"]) for r in catalog["capabilities"]) == sum(len(c.params) for c in visible_capabilities())
    assert {r["input"] for r in catalog["inputs"] if r["exclusive"]} == {n for n, s in INPUT_KIND_REGISTRY.items() if s.exclusive}
    guide = catalog["fieldGuide"]
    assert guide["damageClass"]["builtInTokens"] == list(DAMAGE_CLASS_TOKENS)
    assert "source-only" in guide["damageClass"]["scope"] and "no other tokens" in guide["damageClass"]["scope"]
    assert cards_from(catalog)["configure_item_stats"]["params"]["valueCopper"]["units"] == "copper"
    assert "value" not in cards_from(catalog)["configure_item_stats"]["params"]
    stages = payload["gameplayAuthoringStages"]
    assert [r["name"] for r in stages] == [
        "initial_concept",
        "executable_gameplay_program",
        "final_gameplay_report",
        "same_pass_self_evaluation",
    ]
    assert [r["field"] for r in stages] == [
        "concept",
        "runtimeProgram",
        "realization.description + realization.playerExperience",
        "realization.selfEvaluation",
    ]
    encoded = json.dumps(stages).casefold()
    for phrase in ("non-binding", "not a rejection", "only executable gameplay authority", "same immutable response"):
        assert phrase in encoded
    assert "program_evidence_claims" not in encoded


def cards_from(catalog):
    return {r["fn"]: r for r in catalog["capabilities"]}


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_serialized_author_coherence_advice_keeps_literal_parents_and_all_capabilities(monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    a = {"name": "A", "damage": 16, "useTime": 20}
    b = {"name": "B", "createTile": 239, "placeStyle": 8}
    parents_before = copy.deepcopy((a, b))
    request, user, _ = build_initial_author_request(a, b, a, b, "coherence", model_name="offline-test")
    assert request["response_format"]["type"] == mode
    assert request["messages"][1]["content"] == user
    payload = json.loads(request["messages"][1]["content"])
    concept = payload["requiredJsonShape"]["concept"]
    for field, phrases in {
        "literalSynthesis": ("actual parents", "appearance/identity", "deliberately surreal", "illustrative examples are not additional parents", "every parent capability"),
        "coreMechanic": ("one clear core gameplay loop", "purposeful mechanics", "simple, immediately useful", "supplied progression", "not a capability restriction"),
        "parentAContribution": ("actual parent", "appearance/identity", "purposeful mechanical contribution", "not required"),
        "parentBContribution": ("actual parent", "appearance/identity", "purposeful mechanical contribution", "not required"),
    }.items():
        for phrase in phrases:
            assert phrase in concept[field]
    intent = concept["plannedPlayerActions"][0]["intent"]
    for phrase in (
        "non-binding", "extra control modes", "meaningful utility", "createTile", "does not require",
        "placed target", "worth escrowing", "same generated item", "removes it from inventory",
        "unavailable until", "tile breaks", "returns it", "placement and multiple purposeful actions remain legal",
    ):
        assert phrase in intent
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    expected = {r["fn"]: r for r in compact_capability_catalog()}
    assert _expand_constraint_references(
        {r["fn"]: {k: v for k, v in r.items() if k != "constructionMeaning"}
         for r in catalog["capabilities"]}, catalog["fieldGuide"]["consumerConstraints"]) == expected
    assert set(expected) == {cap.name for cap in visible_capabilities()}
    assert (len(expected), sum(len(r["params"]) for r in expected.values())) == (
        len(visible_capabilities()), sum(len(cap.params) for cap in visible_capabilities()),
    )
    assert (a, b) == parents_before


@pytest.mark.parametrize("fixture_name", ["fishing_platform_tool", "workbench_blade"])
def test_coherence_advice_preserves_explicit_useful_placement_and_nonplacement(monkeypatch, fixture_name):
    from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire

    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    item = build_runtime_fixture(fixture_name)
    before = copy.deepcopy(item)
    compiled_before = compile_runtime_program(item)
    # Constructing the new advisory packet must neither edit an existing design
    # nor turn guidance into a validator prohibition or deterministic selection.
    request, user, _ = build_initial_author_request(item, {}, item, {}, "preserve-design", model_name="offline-test")
    intent = json.loads(user)["requiredJsonShape"]["concept"]["plannedPlayerActions"][0]["intent"]
    assert "placement and multiple purposeful actions remain legal" in intent
    assert request["messages"][1]["content"] == user
    prepared = pipeline._prepare_parsed_author_item(item, response_format=request["response_format"])
    assert prepared == before and item == before
    assert validate_runtime_program(prepared)["ok"]
    compiled_after = compile_runtime_program(prepared)
    assert validate_runtime_wire(compiled_after)["ok"]
    assert compiled_after == compiled_before
    placement = [row for row in prepared["runtimeProgram"]["bindings"] if row["usePolicy"]["action"]["kind"] == "place_item"]
    if fixture_name == "fishing_platform_tool":
        assert placement == [{
            "id": "alternate_place", "input": "alternate_use",
            "usePolicy": {
                "action": {"kind": "place_item", "targetId": "item", "placementCallId": "platform_result"},
                "stackCost": 1, "contactDamage": False,
            },
        }]
        assert next(row["params"] for row in prepared["runtimeProgram"]["calls"] if row["id"] == "platform_result") == {
            "tileId": 19, "placeStyle": 0,
        }
    else:
        assert placement == []


def test_format_repair_with_coherence_advice_preserves_existing_placement(monkeypatch):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    item = build_runtime_fixture("fishing_platform_tool")
    before = copy.deepcopy(item)
    content = json.dumps(item)
    _, recipe_context, _ = build_initial_author_request({}, {}, {}, {}, "syntax-only", model_name="offline-test")
    requests = []

    def respond(request, **kwargs):
        requests.append(request)
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(pipeline, "llm_chat_json", respond)
    prepared, raw = pipeline._repair_malformed_author_json(
        malformed_raw_text=content[:-1] + ",}", parse_error=ValueError("trailing comma"),
        original_recipe_context=recipe_context, model_name="offline-test",
    )
    context = json.loads(requests[0]["messages"][1]["content"])
    intent = context["requiredJsonShape"]["concept"]["plannedPlayerActions"][0]["intent"]
    assert "Repair" not in intent
    assert any("Do not redesign, add, drop" in rule for rule in context["rules"])
    assert context["malformedRawText"] == content[:-1] + ",}"
    assert prepared == before and item == before and raw == content


def test_scoped_repair_does_not_use_coherence_advice_to_remove_valid_placement(monkeypatch):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    item = build_runtime_fixture("fishing_platform_tool")
    before = copy.deepcopy(item)
    stats = _stats(item)
    stats["params"]["damage"] = -1
    replacement = copy.deepcopy(stats)
    replacement["params"]["damage"] = 8
    patch = {
        "note": "Repair only invalid damage", "realizationReplacement": copy.deepcopy(item["realization"]),
        "callsUpsert": [replacement], "bindingIdsDelete": ["alternate_place"], "callIdsDelete": ["platform_result"],
    }
    requests = []

    def respond(request, **kwargs):
        requests.append(request)
        return {"choices": [{"message": {"content": json.dumps(patch)}}]}

    monkeypatch.setattr(pipeline, "llm_chat_json", respond)
    repaired = pipeline.repair_author_item_after_failure(
        item, {}, {}, {}, {}, "frozen-placement", failure_report=validate_runtime_program(item),
    )
    context = json.loads(requests[0]["messages"][1]["content"])
    assert "concept" not in context["requiredJsonShape"]
    assert "one clear core gameplay loop" not in requests[0]["messages"][1]["content"]
    assert validate_runtime_program(repaired)["ok"]
    assert repaired["runtimeProgram"] == before["runtimeProgram"]
    assert repaired["concept"] == before["concept"]
    assert _stats(item)["params"]["damage"] == -1, "repair does not mutate its input"


def test_author_prompt_shape_card_matches_root_object_cardinality_without_provider_schema() -> None:
    card = author_item_prompt_shape_card()
    expected_model_order = ["name", "category", "concept", "runtimeProgram", "realization"]
    assert card["root"] == expected_model_order
    assert list(author_item_response_schema()["properties"]) == expected_model_order

    exported = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts/schemas/author_item_response.schema.json").read_text(encoding="utf-8")
    )
    assert list(exported["properties"]) == expected_model_order
    assert list(author_item_provider_response_schema()["properties"]) == expected_model_order
    assert isinstance(card["concept"], dict)
    assert set(card["concept"]) == {
        "literalSynthesis",
        "coreMechanic",
        "parentAContribution",
        "parentBContribution",
        "playerExperience",
        "plannedPlayerActions",
    }
    planned_action = card["concept"]["plannedPlayerActions"][0]
    assert set(planned_action) == {"input", "intent"}
    assert "runtimeContract" not in card
    assert set(card["realization"]) == {
        "description",
        "playerExperience",
        "selfEvaluation",
    }
    evaluation = card["realization"]["selfEvaluation"]
    assert set(evaluation) == {"planVsProgram", "programVsReport"}
    assert set(evaluation["planVsProgram"]) == {"verdict", "summary", "actionChecks"}
    assert set(evaluation["programVsReport"]) == {"verdict", "summary", "behaviorChecks"}
    assert set(evaluation["planVsProgram"]["actionChecks"][0]) == {
        "plannedIntent",
        "implementedBehavior",
        "runtimeRefs",
        "result",
        "intentionality",
        "reason",
    }
    assert set(evaluation["programVsReport"]["behaviorChecks"][0]) == {
        "runtimeRefs",
        "programBehavior",
        "reportedBehavior",
        "result",
        "reason",
    }
    assert card["runtimeProgram"]["apiVersion"] == "infini.runtime-program.v5"
    assert card["runtimeProgram"]["schema"] == "infini.runtime-program.authoring.v4"
    assert card["runtimeProgram"]["primaryEntityId"] == "exact existing entity id chosen once by the model"
    author_binding = card["runtimeProgram"]["bindings"][0]
    assert set(author_binding) == {"id", "input", "usePolicy"}
    assert set(author_binding["usePolicy"]) == {"action", "stackCost", "contactDamage", "stackConsumeChancePercent"}
    assert set(author_binding["usePolicy"]["action"]) == {"kind", "targetId", "placementCallId", "effectGroupId"}
    assert "role" not in author_binding
    assert "role" not in card["runtimeProgram"]["calls"][0]
    assert isinstance(card["runtimeProgram"]["calls"][0]["params"], dict)
    prompt_payload = build_llm_author_payload({}, {}, {}, {}, "binding-card")
    binding_guide = prompt_payload["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["bindingTarget"]
    assert "bindings[].usePolicy.action.targetId" in binding_guide
    assert "bindings[].target" not in binding_guide

    repair_card = author_item_repair_prompt_shape_card()
    repair_schema = author_item_repair_response_schema()
    repair_binding = repair_card["bindingsUpsert"][0]
    assert set(repair_binding) == {"id", "input", "usePolicy"}
    assert repair_binding["usePolicy"] == author_binding["usePolicy"]
    assert set(repair_card) == set(repair_schema["properties"])
    assert all(
        isinstance(repair_card[key], list)
        for key in (
            "entitiesUpsert",
            "entityIdsDelete",
            "bindingsUpsert",
            "bindingIdsDelete",
            "callsUpsert",
            "callIdsDelete",
        )
    )
    assert "claimsUpsert" not in repair_card
    assert "claimIdsDelete" not in repair_card
    assert isinstance(repair_card["metadataPatch"], dict)
    assert isinstance(repair_card["realizationReplacement"], dict)
    assert isinstance(repair_card["note"], str)
    call = card["runtimeProgram"]["calls"][0]
    assert "existing" in call["target"] and "compatible" in call["target"]
    assert "non-optional" in str(call["params"]) and "conditional" in str(call["params"])
    assert evaluation["planVsProgram"]["verdict"] == "aligned|changed|uncertain"
    assert evaluation["programVsReport"]["verdict"] == "aligned|mismatch|uncertain"
    for part, rows in (("planVsProgram", "actionChecks"), ("programVsReport", "behaviorChecks")):
        assert "uncertain" in evaluation[part][rows][0]["result"]


@pytest.mark.parametrize("rich", [False, True], ids=["source-numeric-parents", "rich-generated-parents"])
def test_author_packet_guide_and_prompt_budget_keep_registry_reachable(rich):
    a = build_runtime_fixture("held_and_deployed") if rich else {"id": "a", "name": "A", "damage": 10, "useTime": 20}
    b = a if rich else {"id": "b", "name": "B", "damage": 20, "useTime": 30}
    catalog = build_llm_author_payload(a, b, a, b, "budget-proof")["runtimeCapabilityContract"]["catalog"]
    guide = catalog["fieldGuide"]
    canonical = runtime_authoring_prompt_field_guide()
    assert {k: guide[k] for k in canonical if k not in {"stackCost", "bindingTarget"}} == {
        k: v for k, v in canonical.items() if k not in {"stackCost", "bindingTarget"}
    }
    assert guide["bindingTarget"].startswith(canonical["bindingTarget"])
    assert "whole generated item" in guide["stackCost"]
    report = planner_prompt_usability_report(a, b, a, b, "budget-proof")
    assert report["ok"] and report["headroom"] >= PLANNER_PROMPT_MIN_HEADROOM_CHARS
    assert report["limit"] == PLANNER_PROMPT_LIMIT_CHARS
    assert report["visibleCapabilities"] == len(visible_capabilities())
    assert report["missingCapabilities"] == report["extraCapabilities"] == []
    assert report["containsWeaponMacro"] is False and report["containsFamilyRouter"] is False


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("pick_power", [0, 50], ids=["intentional-inactive-tool", "active-tool"])
def test_tool_applicability_is_registry_advice_not_an_activation_rewrite(monkeypatch, mode, pick_power):
    from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
    from infini_local.qa.capability_witnesses import build_capability_witness

    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = build_initial_author_request({}, {}, {}, {}, "tool-applicability", model_name="offline-test")
    assert request["response_format"]["type"] == mode
    card = cards_from(json.loads(user)["runtimeCapabilityContract"]["catalog"])["configure_tool"]
    meaning = CAPABILITY_REGISTRY["configure_tool"].params["miningSpeedScale"].description
    assert card["params"]["miningSpeedScale"]["meaning"] == meaning
    for fact in ("while held", "pickPower", "axePowerTooltipPercent", "hammerPower", "> 0", "0.001", "all-zero powers", "no mining-speed effect"):
        assert fact in meaning, "the packet must explain the consumer's joint activation gate"

    doc = build_capability_witness("configure_tool")
    tool = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_tool")
    tool["params"].update(pickPower=pick_power, axePowerTooltipPercent=0, hammerPower=0, miningSpeedScale=2)
    light = copy.deepcopy(next(row for row in build_capability_witness("add_hold_light")["runtimeProgram"]["calls"] if row["fn"] == "add_hold_light"))
    light.update(id="independent_light", target=tool["target"])
    doc["runtimeProgram"]["calls"].append(light)
    before = copy.deepcopy(doc)
    assert validate_runtime_program(doc)["ok"], "advisory non-effect explanation must not ban intentional inactive composition"
    compiled = compile_runtime_program(doc)
    assert validate_runtime_wire(compiled)["ok"]
    assert compiled["gameplay"]["pickPower"] == pick_power
    assert compiled["gameplay"]["axePower"] == compiled["gameplay"]["hammerPower"] == 0
    assert compiled["gameplay"]["miningSpeedScale"] == 2
    assert compiled["gameplay"]["holdLightStrength"] > 0
    assert doc == before


@pytest.mark.parametrize(
    "fn,key,expected",
    [
        pytest.param(fn, key, value, id=fn + "-" + key)
        for fn, key, value in (
            ("heal_owner_on_event", "network_authority", "owner_execute_sync"),
            ("pull_owner_to_event_target", "network_authority", "owner_execute_sync"),
            ("apply_status_on_event", "network_authority", "owner_execute_sync"),
            ("chain_damage_on_event", "network_authority", "owner_execute_sync"),
            ("damage_area_on_event", "network_authority", "server_execute"),
            ("damage_area_on_event", "authority_by_effect", {"on_hit": "owner_execute_sync", "on_crit": "owner_execute_sync"}),
            (
                "pull_on_event",
                "authority_by_effect",
                {"on_hit:target_to_owner": "owner_request_server_execute", "on_hit:target_to_entity": "owner_request_server_execute"},
            ),
        )
    ],
)
def test_authority_facts_are_exact_registry_declarations(fn, key, expected):
    actual = getattr(CAPABILITY_REGISTRY[fn], key)
    if key == "authority_by_effect":
        assert dict(actual) == expected if fn != "pull_on_event" else all(actual[k] == v for k, v in expected.items())
    else:
        assert actual == expected


UNIT_MEANINGS = {
    "configure_item_stats": {"knockback": "Item.knockBack", "scale": "1 unchanged"},
    "configure_item_contact_hitbox": {"contactForgivenessPx": "each side"},
    "apply_generated_buff_on_use": {
        "moveSpeedBonusFactor": "Player.moveSpeed",
        "jumpSpeedBonusPxPerTick": "pixels/tick",
        "manaRegenBonusPoints": "Player.manaRegen",
        "miningSpeedMultiplier": "pickSpeed",
        "lightStrength": "RGB",
    },
    "configure_tool": {"pickPower": "tooltip", "hammerPower": "tooltip", "miningSpeedScale": "pickSpeed"},
    "configure_tile_placement": {"placeStyle": "Item.placeStyle"},
    "require_use_condition": {"condition": "thresholds include equality"},
    "add_hold_light": {"strength": "RGB"},
    "emit_light_while_active": {"strength": "RGB"},
    "configure_accessory": {
        "manaRegenBonusPoints": "Player.manaRegenBonus",
        "aggroPoints": "Player.aggro",
        "genericArmorPenetrationPoints": "armor",
        "lightStrength": "RGB",
    },
    "configure_armor": {
        "manaRegenBonusPoints": "Player.manaRegenBonus",
        "aggroPoints": "Player.aggro",
        "genericArmorPenetrationPoints": "armor",
        "lightStrength": "RGB",
    },
    "configure_spawn": {"velocity": "initial velocity", "count": "root binding"},
    "set_projectile_hitbox": {"drawScale": "visual scale"},
    "set_projectile_damage": {"knockback": "Projectile.knockBack"},
    "set_projectile_collision": {"updatesPerTick": "per world tick", "immunity": "engine"},
    "move_gravity_arc": {"gravityVelocityPerUpdate": "per projectile update"},
    "move_sine_homing": {"waveVelocityCoefficient": "0.03"},
    "move_accelerate": {"speedMultiplierPerUpdate": "per projectile update"},
    "move_spiral": {"turnRadiansPerUpdate": "per projectile update"},
    "move_expanding_wave": {"scaleGrowthPerUpdate": "per projectile update"},
    "target_and_fire": {"sameTargetBias": "0.9", "rangeTiles": "hard geometric"},
    "pull_on_event": {"strength": "velocity", "radiusTiles": "no active direct target"},
    "heal_owner_on_event": {"damageFraction": "0.15 = 15%"},
}
EXPLICIT_MEANINGS = [
    ("charge_then_release", "powerMultiplier", "release velocity"),
    ("move_phase", "phaseStrength", "alpha"),
    ("move_player_on_use", "safeTileOnly", "ignored for recall_home"),
    ("move_owner_on_event", "safeTileOnly", "not a general hazard check"),
    ("configure_item_stats", "manaCost", "Base Item.mana"),
    ("configure_item_stats", "craftYield", "maxStack"),
    ("restore_resources_on_use", "usesPotionRules", "Quick Heal"),
    ("configure_item_use", "customHeldSprite", "not gameplay release timing"),
    ("configure_accessory", "ammoSaveChancePercent", "any weapon"),
    ("configure_accessory", "ammoSaveChancePercent", "CanConsumeAmmo"),
    ("configure_accessory", "manaRegenBonusPoints", "not mana/s"),
    ("configure_item_stats", "useAnimationTicks", "independent"),
    ("configure_item_stats", "useTimeTicks", "interval"),
    ("set_projectile_hitbox", "hitboxScale", "1 unchanged"),
    ("move_accelerate", "speedMultiplierPerUpdate", "1 unchanged"),
    ("charge_then_release", "powerMultiplier", "1 unchanged"),
    ("configure_item_stats", "damageClass", "DamageClass.FullName"),
    ("configure_item_stats", "damageClass", "not item FullName"),
    ("set_projectile_damage", "damageClass", "DamageClass.FullName"),
    ("set_projectile_damage", "damageClass", "not item FullName"),
    ("damage_area_on_event", "damageMultiplier", "item_body"),
    ("damage_area_on_event", "damageMultiplier", "configure_item_stats.damage"),
    ("damage_area_on_event", "damageMultiplier", "set_projectile_damage.damage"),
    ("damage_area_on_event", "damageMultiplier", "damageDone"),
    ("damage_area_on_event", "damageMultiplier", "at least 1"),
    ("damage_area_on_event", "damageMultiplier", "before target defense"),
    ("chain_damage_on_event", "damageMultiplier", "item_body"),
    ("chain_damage_on_event", "damageMultiplier", "configure_item_stats.damage"),
    ("chain_damage_on_event", "damageMultiplier", "set_projectile_damage.damage"),
    ("chain_damage_on_event", "damageMultiplier", "damageDone"),
    ("chain_damage_on_event", "damageMultiplier", "at least 1"),
    ("chain_damage_on_event", "damageMultiplier", "before target defense"),
    ("set_projectile_collision", "immunity", "unscaled"),
    ("set_projectile_collision", "immunity", "once"),
    ("set_projectile_collision", "immunity", "0..600"),
    ("set_projectile_collision", "immunity", "owner"),
    ("set_projectile_collision", "immunity", "updatesPerTick"),
    ("configure_accessory", "lifeRegenHpPerSecond", "+2"),
    ("configure_accessory", "lifeRegenHpPerSecond", "+1 HP/s"),
    ("configure_accessory", "lifeRegenHpPerSecond", "-2"),
    ("configure_accessory", "lifeRegenHpPerSecond", "-1 HP/s"),
    ("move_drift", "velocityRetention", "updatesPerTick"),
    ("configure_spawn", "velocity", "No peer reroll"),
]


@pytest.mark.parametrize(
    "fn,name,phrase",
    [pytest.param(fn, name, p, id=fn + "-" + name + "-" + p) for fn, params in UNIT_MEANINGS.items() for name, p in params.items()]
    + [pytest.param(fn, n, p, id=fn + "-" + n + "-" + p) for fn, n, p in EXPLICIT_MEANINGS],
)
def test_serialized_numeric_card_explains_exact_consumer_meaning(packet, fn, name, phrase):
    row = cards_from(packet[1]["runtimeCapabilityContract"]["catalog"])[fn]["params"][name]
    meaning = row.get("meaning") or CAPABILITY_REGISTRY["configure_accessory"].params.get(name).description
    assert phrase in meaning


# Units that are raw engine coefficients have no percent conversion layer.
RAW_COEFFICIENTS = {
    "configure_item_stats": ("knockback",),
    "set_projectile_damage": ("knockback",),
    "configure_tool": ("miningSpeedScale",),
    "apply_generated_buff_on_use": ("miningSpeedMultiplier", "lightStrength", "moveSpeedBonusFactor", "manaRegenBonusPoints"),
    "configure_accessory": ("manaRegenBonusPoints", "aggroPoints", "lightStrength"),
    "configure_armor": ("manaRegenBonusPoints", "aggroPoints", "lightStrength", "setBonuses.manaRegenBonusPoints", "setBonuses.aggroPoints"),
    "add_hold_light": ("strength",),
    "emit_light_while_active": ("strength",),
    "move_slow_homing": ("homingStrength",),
    "move_sine_homing": ("homingStrength", "waveVelocityCoefficient"),
    "move_proximity_missile": ("homingStrength",),
    "move_drift": ("velocityRetention",),
    "move_phase": ("phaseStrength",),
    "move_vortex_orb": ("pullStrength",),
    "move_blackhole_pull": ("pullStrength",),
    "move_accelerate": ("speedMultiplierPerUpdate",),
    "target_and_fire": ("sameTargetBias",),
    "pull_on_event": ("strength",),
}


@pytest.mark.parametrize("fn,name", [pytest.param(fn, n, id=fn + "-" + n) for fn, names in RAW_COEFFICIENTS.items() for n in names])
def test_raw_coefficients_have_identity_wire_conversion(fn, name):
    parts = name.split(".")
    spec = CAPABILITY_REGISTRY[fn].params[parts[0]]
    for part in parts[1:]:
        spec = spec.properties[part]
    assert "engine units" in spec.units.lower()
    assert spec.wire_divisor == spec.wire_multiplier == 1
    value = 1.770282212988338
    assert value * 100 / 100 != value
    assert CAPABILITY_REGISTRY["apply_generated_buff_on_use"].params["moveSpeedBonusFactor"].to_wire(value).hex() == value.hex()


@pytest.mark.parametrize(
    "fn,name",
    [
        pytest.param(fn, n, id=fn + "-" + n)
        for fn, n in (
            ("move_boomerang", "returnSpeed"),
            ("move_returning_glaive", "returnSpeed"),
            ("move_accelerate", "maxSpeed"),
            ("move_flail_tether", "returnSpeed"),
            ("move_yoyo_hover", "returnSpeed"),
        )
    ],
)
def test_serialized_speed_units_are_projectile_updates(packet, fn, name):
    assert cards_from(packet[1]["runtimeCapabilityContract"]["catalog"])[fn]["params"][name]["units"] == "pixels/projectile update"


@pytest.mark.parametrize(
    "section,identity,field,phrase",
    [
        pytest.param(*row, id="-".join(row[:3]) + "-" + str(i))
        for i, row in enumerate(
            (
                ("fieldGuide", "stackCost", "", "Projectile return does not refund"),
                ("fieldGuide", "stackCost", "", "stackCost=0"),
                ("fieldGuide", "stackCost", "", "whole generated item"),
                ("fieldGuide", "stackCost", "", "stackCost=1"),
                ("fieldGuide", "bindingTarget", "", "contactDamage=true"),
                ("fieldGuide", "bindingTarget", "", "bindings[].usePolicy.action.targetId"),
                ("bindingActions", "place_item", "constructionMeaning", "stackCost=1"),
                ("bindingActions", "place_item", "constructionMeaning", "returned"),
                ("bindingActions", "place_item", "constructionMeaning", "item_body.on_use"),
                ("bindingActions", "apply_item_effects", "does", "only active binding"),
                ("bindingActions", "use_item_body", "does", "never pair it with spawn_entity"),
                ("inputs", "primary_use", "constructionMeaning", "does not require use_item_body"),
                ("events", "on_use", "constructionMeaning", "spawned entity"),
                ("events", "on_expire", "constructionMeaning", "on_expire"),
                ("entityKinds", "item_body", "requiredComponents", "configure_item_stats"),
                ("entityKinds", "stationary_projectile", "constructionMeaning", "target_and_fire"),
                ("fieldGuide", "paramNotation", "", "15 means 15%, not 0.15"),
            )
        )
    ]
    + [
        pytest.param("fieldGuide", "paramNotation", "", p, id="numeric-guide-" + p)
        for p in (
            "per projectile update",
            "updatesPerTick",
            "world ticks",
            "updatesPerTick updates",
            "immunity.localCooldown",
            "15",
            "0.15",
            "bonusPercent",
            "CritChancePercentagePoints",
            "manaCostReductionPercentagePoints",
            "damageReductionPercentagePoints",
            "ammoSaveChancePercent",
            "damageMultiplier=1",
            "AoE/chain floor at 1",
            "damageFraction=0.15",
            "homingStrength=0.15",
            "pierce=-1",
            "tileId/wallId=-1",
            "Default receives no Generic",
            "Summon crit is nonstandard",
        )
    ],
)
def test_serialized_construction_guide_keeps_specific_obligations(packet, section, identity, field, phrase):
    catalog = packet[1]["runtimeCapabilityContract"]["catalog"]
    if section == "fieldGuide":
        value = catalog[section][identity]
    else:
        key = {"bindingActions": "action", "events": "event", "inputs": "input", "entityKinds": "kind"}[section]
        value = next(r[field] for r in catalog[section] if r[key] == identity)
    assert phrase in value
    assert "bindings[].target" not in catalog["fieldGuide"]["bindingTarget"]
    assert "free_projectile" in {r["kind"] for r in catalog["entityKinds"]}
    immunity = cards_from(catalog)["set_projectile_collision"]["params"]["immunity"]["shape"]
    cooldown = next(row["properties"]["localCooldown"] for row in immunity["oneOf"] if row.get("type") == "object")
    assert cooldown["minimum"] == 0 and cooldown["maximum"] == 600
    assert "per projectile update" in cards_from(catalog)["move_drift"]["does"]


def test_proximity_expiration_is_explicit_without_synthetic_hit() -> None:
    movement = CAPABILITY_REGISTRY["move_proximity_missile"].prompt_card()["does"]
    expiration = EVENT_KIND_REGISTRY["on_expire"].prompt_card()["does"]
    author_rule = realization_execution_truth_for_llm()["terminationEvents"]
    for description in (movement, expiration, author_rule):
        assert "proximity" in description.lower()
    assert "on_hit" in movement and "actual hit" in movement.lower()
    assert "natural" in expiration.lower() and "natural" in author_rule.lower()


def test_generated_parity_table_shows_set_key_pattern_not_boolean_range() -> None:
    text = (Path(__file__).resolve().parents[2] / "docs/PRIMITIVE_PARITY_RU.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| setKey |"))
    assert r"^[a-z0-9_]{0,48}$" in row
    assert "| bounded_text |  |" in row
    assert "| bool |" not in row


def test_canonical_parity_document_contains_engine_units_and_loss_boundaries() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs/PRIMITIVE_PARITY_RU.md").read_text(encoding="utf-8")
    assert "019ff01" in text and "25caddf" in text
    assert "add_equipment_damage_bonus" in text and "additive_percent" in text
    assert "armor.setBonusMagicDamage" in text and "matching_armor_set" in text
    assert "meleeDamageBonusPercent" not in text
    assert "extraUpdates > 0" in text
    assert "held generatedBuff" in text
    assert "OreSenseRadiusTiles" in text and "oreSenseEnabled" in text
    assert "RuntimeParamsSpec.IntervalTicks" in text
    inventory = (root / "docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md").read_text(encoding="utf-8")
    assert "PRIMITIVE_PARITY_RU.md" in inventory


def _stats(item):
    return next(row for row in item["runtimeProgram"]["calls"] if isinstance(row, dict) and row["fn"] == "configure_item_stats")


def _response_format():
    return {"type": "json_schema", "json_schema": {"schema": author_item_provider_response_schema()}}


@pytest.mark.parametrize(
    "mode,wrapper,omitted",
    [
        pytest.param("json_schema", True, True, id="schema-declared-nullable"),
        pytest.param("json_object", True, False, id="plain-json"),
        pytest.param("off", True, False, id="no-format"),
        pytest.param("json_schema", False, False, id="schema-without-nullable-wrapper"),
    ],
)
def test_nullable_projection_requires_actual_schema_and_preserves_invalid_neighbours(mode, wrapper, omitted):
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"].update(manaCost=None, notARegisteredParameter=None, damage=None)
    item["runtimeProgram"]["calls"].insert(0, None)
    before = copy.deepcopy(item)
    response_format = _response_format() if mode == "json_schema" else ({"type": mode} if mode != "off" else None)
    if mode == "json_schema" and not wrapper:
        variants = response_format["json_schema"]["schema"]["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["anyOf"]
        variant = next(r for r in variants if r["properties"]["fn"]["const"] == "configure_item_stats")
        params = variant["properties"]["params"]["properties"]
        params["manaCost"] = params["manaCost"]["anyOf"][0]
    projected = project_provider_author_item_to_local(item, response_format=response_format)
    assert pipeline._prepare_parsed_author_item(item, response_format=response_format) == projected
    params = _stats(projected)["params"]
    assert ("manaCost" not in params) is omitted
    assert params["notARegisteredParameter"] is None and params["damage"] is None
    assert projected["runtimeProgram"]["calls"][0] is None and len(projected["runtimeProgram"]["calls"]) == len(
        item["runtimeProgram"]["calls"]
    )
    assert item == before and not validate_runtime_program(projected)["ok"]
    if mode == "off":
        assert pipeline._prepare_parsed_author_item(item) == before


@pytest.mark.parametrize(
    "mode,actual,malformed",
    [
        pytest.param(mode, actual, False, id=mode + "-effective-" + (actual or "off"))
        for mode, actual in (
            ("json_schema", "json_schema"),
            ("json_object", "json_object"),
            ("off", ""),
            ("json_schema", "json_object"),
            ("json_schema", ""),
        )
    ]
    + [pytest.param("json_schema", "json_schema", True, id="schema-format-repair")],
)
def test_author_entrypoint_uses_effective_format_preserves_raw_and_carries_mode_to_repair(monkeypatch, mode, actual, malformed):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    content = json.dumps(item)
    raw = content[:-1] + ",}" if malformed else content
    responses = iter([raw, content] if malformed else [content])
    requests = []

    def respond(request, **kwargs):
        requests.append(request)
        return {"choices": [{"message": {"content": next(responses)}}], "_debug": {"responseFormatType": actual}}

    monkeypatch.setattr(pipeline, "llm_chat_json", respond)
    result = pipeline.try_llm_plan({}, {}, {}, {}, "nullable-test")
    assert result is not None
    assert ("manaCost" not in _stats(result)["params"]) is (actual == "json_schema")
    assert validate_runtime_program(result)["ok"] is (actual == "json_schema")
    assert result["debug"]["llmRawOutput"] == raw[:12000]
    assert [r["_infini_stage"] for r in requests] == (["planner", "author_repair"] if malformed else ["planner"])
    if malformed:
        assert result["debug"]["gameplayFormatRepairRawOutput"] == content[:12000]


@pytest.mark.parametrize(
    "source_schema,mode,actual,accepted",
    [
        pytest.param(*r, id=("schema" if r[0] else "plain") + "-" + r[1] + "-" + str(i))
        for i, r in enumerate(
            (
                (True, "json_schema", "json_schema", True),
                (False, "json_object", "json_object", True),
                (False, "off", "", True),
                (False, "json_schema", "json_object", True),
                (False, "json_schema", None, False),
            )
        )
    ],
)
def test_format_repair_preserves_source_contract_without_mode_upgrade(monkeypatch, source_schema, mode, actual, accepted):
    from infini_local.core.errors import PlannerUnavailable

    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    item = build_runtime_fixture("workbench_blade")
    _stats(item)["params"]["manaCost"] = None
    content = json.dumps(item)
    response = {"choices": [{"message": {"content": content}}]}
    if actual is not None:
        response["_debug"] = {"responseFormatType": actual}
    monkeypatch.setattr(pipeline, "llm_chat_json", lambda *a, **kw: response)
    args = {
        "malformed_raw_text": content[:-1] + ",}",
        "parse_error": ValueError("trailing comma"),
        "original_recipe_context": "{}",
        "model_name": "offline-test",
        "source_response_format": _response_format() if source_schema else None,
    }
    if not accepted:
        with pytest.raises(PlannerUnavailable, match="changed recoverable authored fields"):
            pipeline._repair_malformed_author_json(**args)
    else:
        prepared, raw = pipeline._repair_malformed_author_json(**args)
        assert ("manaCost" not in _stats(prepared)["params"]) is source_schema
        assert raw == content


@pytest.mark.parametrize(
    "mode,actual,mana,variant",
    [
        pytest.param(mode, actual, mana, "nullable", id=mode + "-effective-" + (actual or "off") + "-frozen-mana-" + str(mana))
        for mode, actual in (("json_schema", "json_schema"), ("json_object", "json_object"), ("off", ""), ("json_schema", "json_object"))
        for mana in (None, 7)
    ]
    + [
        pytest.param("json_object", None, 7, "invalid-frozen-mana", id="filter-before-final-range-validation"),
        pytest.param("json_schema", None, 7, None, id="null-realization"),
        pytest.param("json_schema", None, 7, {}, id="empty-realization"),
        pytest.param("json_schema", None, 7, {"description": "incomplete"}, id="incomplete-realization"),
    ],
)
def test_repair_entrypoint_preserves_frozen_semantics_raw_and_realization_guard(monkeypatch, mode, actual, mana, variant):
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines.author_item_contract import strict_author_item_repair_report

    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    item = build_runtime_fixture("workbench_blade")
    stats = _stats(item)
    if mana is None:
        stats["params"].pop("manaCost", None)
    else:
        stats["params"]["manaCost"] = mana
    stats["params"]["damage"] = -1
    replacement = copy.deepcopy(stats)
    replacement["params"].update(damage=42, manaCost=-1 if variant == "invalid-frozen-mana" else None)
    shape_guard = not isinstance(variant, str)
    patch = {
        "note": "Repair damage",
        "realizationReplacement": variant if shape_guard else copy.deepcopy(item["realization"]),
        "callsUpsert": [replacement],
    }
    if variant == "nullable":
        patch["metadataPatch"] = None
    if variant == "invalid-frozen-mana":
        assert not strict_author_item_repair_report(patch)["ok"]
    response = {"choices": [{"message": {"content": json.dumps(patch)}}]}
    if actual is not None:
        response["_debug"] = {"responseFormatType": actual}
    monkeypatch.setattr(pipeline, "llm_chat_json", lambda *a, **kw: response)
    args = (item, {}, {}, {}, {}, "repair-contract")
    if shape_guard or (variant == "nullable" and actual != "json_schema"):
        with pytest.raises(PlannerUnavailable):
            pipeline.repair_author_item_after_failure(*args, failure_report=validate_runtime_program(item))
    else:
        result = pipeline.repair_author_item_after_failure(*args, failure_report=validate_runtime_program(item))
        assert validate_runtime_program(result)["ok"] and _stats(result)["params"]["damage"] == 42
        assert ("manaCost" in _stats(result)["params"]) is (mana is not None)
        if mana is not None:
            assert _stats(result)["params"]["manaCost"] == mana
        if variant == "nullable":
            assert result["debug"]["gameplayRepairRawPatch"] == patch


@pytest.mark.parametrize("stage", ["author", "format", "repair"])
@pytest.mark.parametrize("mode", ["json_schema", "json_object", "off"])
def test_serialized_stage_prose_explains_nullable_transport_only_with_schema(monkeypatch, stage, mode):
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "resolve_llm_model", lambda: "offline-test")
    requests = []

    class Captured(BaseException):
        pass

    def capture(request, **kwargs):
        requests.append(request)
        raise Captured()

    monkeypatch.setattr(pipeline, "llm_chat_json", capture)
    with pytest.raises(Captured):
        if stage == "author":
            pipeline.try_llm_plan({}, {}, {}, {}, "prose")
        elif stage == "format":
            pipeline._repair_malformed_author_json(
                malformed_raw_text="{", parse_error=ValueError(), original_recipe_context="{}", model_name="offline-test"
            )
        else:
            item = build_runtime_fixture("workbench_blade")
            _stats(item)["params"]["damage"] = -1
            pipeline.repair_author_item_after_failure(item, {}, {}, {}, {}, "prose", failure_report=validate_runtime_program(item))
    # Inspect exactly the serialized messages passed to the transport seam.
    system = json.loads(json.dumps(requests[0]))["messages"][0]["content"]
    assert ("nullable transport" in system) == (mode == "json_schema")
    if mode == "json_schema":
        assert "omission" in system
        assert "array elements" in system
        if stage == "repair":
            assert "no change" in system
        else:
            assert "Omission retains its meaning in the requested output contract" in system
