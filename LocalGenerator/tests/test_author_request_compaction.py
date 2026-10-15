"""Lossless prompt metadata sharing and the real strict-provider inverse seam."""
from __future__ import annotations
from prompt_packet_helpers import request_dossier, dossier_text

import copy
import json
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines import author_item_contract as contract
from infini_local.pipelines import combine_balance as balance
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines import llm_authoring_prompt as prompt
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_codex_subscription_contract import _encode_nullable_fixture
from test_gameplay_repair_readonly_context import _CapturedBeforeTransport, _offline_builder


def _expand_constraint_references(value, profiles):
    if isinstance(value, dict):
        return {key: copy.deepcopy(profiles[child])
                if key == "consumerConstraint" and isinstance(child, str)
                else _expand_constraint_references(child, profiles)
                for key, child in value.items()}
    if isinstance(value, list):
        return [_expand_constraint_references(child, profiles) for child in value]
    return copy.deepcopy(value)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_serialized_lifetime_guidance_matches_author_repair_and_existing_gates(monkeypatch, mode):
    captured = []

    def stop(request, **_kwargs):
        captured.append(copy.deepcopy(request))
        raise _CapturedBeforeTransport()

    _offline_builder(monkeypatch, mode, stop)
    parents = ({"name": "A", "damage": 52, "useTime": 10},
               {"name": "B", "damage": 0, "useTime": 20})
    before = copy.deepcopy(parents)
    request, serialized, _ = author.build_initial_author_request(
        *parents, {}, {}, "lifetime-guidance", model_name="offline-readonly-context")
    assert request["response_format"]["type"] == mode
    assert dossier_text(request) == serialized
    packet = json.loads(serialized)
    spec = CAPABILITY_REGISTRY["set_projectile_lifetime"].params["lifetimeTicks"]
    assert (spec.minimum, spec.maximum) == (1, 36000)
    bounds = {"minimum": spec.minimum, "maximum": spec.maximum}
    assert packet["balanceCorridor"]["broadEnvelope"]["lifetimeTicks"] == bounds
    card = next(row for row in packet["runtimeCapabilityContract"]["catalog"]["capabilities"]
                if row["fn"] == "set_projectile_lifetime")
    assert (card["params"]["lifetimeTicks"]["min"], card["params"]["lifetimeTicks"]["max"]) == (1, 36000)

    item = build_runtime_fixture("workbench_blade")
    index, lifetime = next((index, row) for index, row in enumerate(item["runtimeProgram"]["calls"])
                           if row["fn"] == "set_projectile_lifetime")
    lifetime["params"]["lifetimeTicks"] = 36000
    local_schema = contract.author_item_response_schema()
    provider_schema = contract.author_item_provider_response_schema()
    assert Draft202012Validator(local_schema).is_valid(item)
    provider_item = _encode_nullable_fixture(item, local_schema)
    assert Draft202012Validator(provider_schema).is_valid(provider_item)
    assert validate_runtime_program(item)["ok"]
    wire = compile_runtime_program(item)
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                   authored_document=item, final_document=wire)["ok"]
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == lifetime["target"])
    assert entity["lifetimeTicks"] == 36000
    accepted_before = copy.deepcopy(item)
    for ticks in (1, 21600):
        lifetime["params"]["lifetimeTicks"] = ticks
        retained = compile_runtime_program(item)
        retained_entity = next(row for row in retained["runtimeProgram"]["entities"]
                               if row["id"] == lifetime["target"])
        assert retained_entity["lifetimeTicks"] == ticks
        assert validate_runtime_wire(retained)["ok"]
    lifetime["params"]["lifetimeTicks"] = 36000
    assert item == accepted_before

    lifetime["params"]["lifetimeTicks"] = 36001
    assert not Draft202012Validator(local_schema).is_valid(item)
    provider_item["runtimeProgram"]["calls"][index]["params"]["lifetimeTicks"] = 36001
    assert not Draft202012Validator(provider_schema).is_valid(provider_item)
    invalid_before = copy.deepcopy(item)
    failure = validate_runtime_program(item)
    path = f"$.runtimeProgram.calls[{index}].params.lifetimeTicks"
    assert not failure["ok"]
    assert any(row["path"] == path and row["code"] == "shape_maximum"
               for row in failure["errors"]), failure
    with pytest.raises(ValueError):
        compile_runtime_program(item)
    entity["lifetimeTicks"] = 36001
    assert not validate_runtime_wire(wire)["ok"]
    with pytest.raises(_CapturedBeforeTransport):
        author.repair_author_item_after_failure(
            item, *parents, {}, {}, "lifetime-guidance", failure_report=failure)
    assert len(captured) == 1
    repair_request = captured[0]
    assert repair_request["response_format"]["type"] == mode
    repair = request_dossier(repair_request)
    repair_card = next(row for row in repair["existingBrokenCapabilityCards"]
                       if row["fn"] == "set_projectile_lifetime")
    assert (repair_card["params"]["lifetimeTicks"]["min"],
            repair_card["params"]["lifetimeTicks"]["max"]) == (1, 36000)
    assert repair["acceptedItemContext"]["runtimeProgram"] == item["runtimeProgram"]
    assert repair["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": lifetime["id"], "paths": ["params.lifetimeTicks"]}]
    assert item == invalid_before and parents == before

    # Syntax-only Repair retains this exact recipe fact instead of rebuilding it.
    with pytest.raises(_CapturedBeforeTransport):
        author._repair_malformed_author_json(
            malformed_raw_text=json.dumps(item)[:-1] + ",}", parse_error=ValueError("trailing comma"),
            original_recipe_context=serialized, model_name="offline-readonly-context")
    format_packet = request_dossier(captured[1])
    assert format_packet["originalRecipeContext"]["balanceCorridor"] == packet["balanceCorridor"]

    # A different declared maximum must reach the real packet, not a copied cap.
    cap = CAPABILITY_REGISTRY["set_projectile_lifetime"]
    changed = replace(cap, params={**cap.params, "lifetimeTicks": replace(spec, maximum=21000)})
    monkeypatch.setattr(balance, "CAPABILITY_REGISTRY", {**CAPABILITY_REGISTRY, cap.name: changed})
    variant_request, variant_serialized, _ = author.build_initial_author_request(
        *parents, {}, {}, "lifetime-guidance", model_name="offline-readonly-context")
    variant_packet = json.loads(variant_serialized)
    assert variant_packet["balanceCorridor"]["broadEnvelope"]["lifetimeTicks"]["maximum"] == 21000
    variant_packet["balanceCorridor"]["broadEnvelope"]["lifetimeTicks"]["maximum"] = spec.maximum
    assert variant_packet == packet
    variant_request["messages"][2]["content"] = request["messages"][2]["content"]
    assert variant_request == request  # System, parents, other guidance and transport stay exact.


def test_shared_constraints_expand_to_every_literal_registry_rule_without_mutation():
    originals = {name: cap.author_prompt_card() for name, cap in CAPABILITY_REGISTRY.items()}
    catalog = prompt.sharp_engine_fn_catalog_for_llm()
    profiles = catalog["fieldGuide"]["consumerConstraints"]
    references = []
    for card in catalog["capabilities"]:
        for name, param in card["params"].items():
            source = originals[card["fn"]]["params"][name]
            if "consumerConstraint" not in source:
                assert "consumerConstraint" not in param
                continue
            references.append(param["consumerConstraint"])
            assert profiles[param["consumerConstraint"]] == source["consumerConstraint"]
    assert set(references) == set(profiles)
    assert len(profiles) < len(references)
    assert originals == {name: cap.author_prompt_card() for name, cap in CAPABILITY_REGISTRY.items()}
    # The double rule is retained separately; it is not recast as a float32 guard.
    doubles = [value for value in profiles.values() if value["storage"] == "float64"]
    assert len(doubles) == 1 and doubles[0]["rule"] == "finite_double_no_normalization"


def test_new_constraint_metadata_gets_its_own_definition_without_profile_guessing():
    first = {"storage": "future_storage", "neutral": 7, "wireProjection": {"divisor": 37},
             "meaning": "A new literal rule which must not match an existing profile."}
    second = {**first, "neutral": 8}
    cards = [{"params": {"one": {"consumerConstraint": copy.deepcopy(first)},
                          "two": {"consumerConstraint": copy.deepcopy(first)},
                          "three": {"nested": {"consumerConstraint": copy.deepcopy(second)}}}}]
    profiles = prompt._share_consumer_constraints(cards)
    params = cards[0]["params"]
    assert len(profiles) == 2
    assert params["one"]["consumerConstraint"] == params["two"]["consumerConstraint"]
    assert profiles[params["one"]["consumerConstraint"]] == first
    assert profiles[params["three"]["nested"]["consumerConstraint"]] == second


def test_provider_omits_only_schema_annotations_and_preserves_literal_properties():
    literal = {"description": "authored literal", "x-infini-units": "also literal", "if": {"const": 3}}
    local = {
        "type": "object", "additionalProperties": False, "description": "schema annotation",
        "properties": {
            "description": {"type": "string", "minLength": 2, "description": "field annotation"},
            "x-infini-real-field": {"const": literal, "x-infini-reference": {"opaque": True}},
        },
        "required": ["description", "x-infini-real-field"],
    }
    before = copy.deepcopy(local)
    provider = contract._provider_strict_projection(local, omit_annotations=True)
    assert "description" not in provider
    assert set(provider["properties"]) == {"description", "x-infini-real-field"}
    assert provider["properties"]["description"] == {"type": "string", "minLength": 2}
    assert provider["properties"]["x-infini-real-field"] == {"const": literal, "type": "object"}
    for value in [{"description": "ok", "x-infini-real-field": literal},
                  {"description": "x", "x-infini-real-field": literal},
                  {"description": "ok", "x-infini-real-field": {}}]:
        assert Draft202012Validator(local).is_valid(value) == Draft202012Validator(provider).is_valid(value)
    assert local == before


@pytest.mark.parametrize("omit_annotations", [False, True])
def test_nullable_inverse_accepts_both_exact_projection_policies(omit_annotations):
    local = {"type": "object", "additionalProperties": False, "required": [],
             "properties": {"optional": {"type": "number", "minimum": 2,
                                           "description": "Visual may use this guidance"}}}
    provider = contract._provider_strict_projection(local, omit_annotations=omit_annotations)
    wrapper = provider["properties"]["optional"]["anyOf"][0]
    assert ("description" in wrapper) is not omit_annotations
    response_format = {"type": "json_schema", "json_schema": {"schema": provider}}
    assert contract.project_provider_nullable_optionals_to_local(
        {"optional": None}, local, response_format=response_format) == {}
    wrapper["minimum"] = 1
    assert contract.project_provider_nullable_optionals_to_local(
        {"optional": None}, local, response_format=response_format) == {"optional": None}


# Capability execution belongs to registry_vertical_contract. This adapter is
# recursive over schema shapes, so exercise those shapes instead of every fn.
@pytest.mark.parametrize("fn,params,omitted", [
    pytest.param("configure_item_stats", {}, "manaCost", id="optional-item-leaf"),
    pytest.param("move_straight", {}, None, id="omitted-noarg-params"),
    pytest.param("set_projectile_collision", {"immunity": {"localCooldown": 37}}, None, id="typed-union"),
    pytest.param("configure_armor", {"setBonuses": {"minionSlotsBonus": 2}}, None, id="nested-optional-object"),
    pytest.param("spawn_entity_on_event", {"when": {"everyTicks": 30}}, None, id="event-object-branch"),
])
def test_compact_provider_roundtrips_structural_witnesses(fn, params, omitted):
    item = build_capability_witness(fn)
    call = next(row for row in item["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    if params:
        call["params"].update(params)
    if omitted:
        call["params"].pop(omitted)
    assert validate_runtime_program(item)["ok"]
    local = contract.author_item_response_schema()
    provider = contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(item, local)
    before = json.dumps(encoded, ensure_ascii=False, sort_keys=True)
    assert Draft202012Validator(provider).is_valid(encoded)
    restored = contract.project_provider_author_item_to_local(
        encoded, response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert restored == item
    assert json.dumps(encoded, ensure_ascii=False, sort_keys=True) == before


def test_source_units_keep_zero_null_and_exact_namespaces_without_selecting_capabilities():
    packets = [{"raw": {"item": {"axePower": 0}, "generatedParent": {
        "accessory": {"movementSpeed": None}, "armor": {"lifeRegen": 0},
        "gameplay": {"movementSpeed": 55, "generatedBuff": {"lifeRegen": 2}},
    }}}]
    before = copy.deepcopy(packets)
    glossary = prompt.source_wire_units_for_llm(packets)
    actual = {(row["source"], row["fn"], field) for row in glossary["scopes"] for field in row["fields"]}
    assert actual == {
        ("raw.item", "configure_tool", "axePower"),
        ("raw.generatedParent.accessory", "configure_accessory", "movementSpeed"),
        ("raw.generatedParent.armor", "configure_armor", "lifeRegen"),
        ("raw.generatedParent.gameplay.generatedBuff", "apply_generated_buff_on_use", "lifeRegen"),
    }
    assert prompt.source_wire_units_for_llm([])["scopes"] == []
    assert packets == before
    assert {row["fn"] for row in prompt.sharp_engine_fn_catalog_for_llm()["capabilities"]} == {name for name, cap in CAPABILITY_REGISTRY.items() if cap.prompt_visible and cap.decision == "expose"}
