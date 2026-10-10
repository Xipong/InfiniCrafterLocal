"""Lossless prompt metadata sharing and the real strict-provider inverse seam."""
from __future__ import annotations

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, validate_runtime_program
from infini_local.pipelines import author_item_contract as contract
from infini_local.pipelines import llm_authoring_prompt as prompt
from infini_local.qa.capability_witnesses import build_capability_witness
from test_codex_subscription_contract import _encode_nullable_fixture


def _expand_constraint_references(value, profiles):
    if isinstance(value, dict):
        return {key: copy.deepcopy(profiles[child])
                if key == "consumerConstraint" and isinstance(child, str)
                else _expand_constraint_references(child, profiles)
                for key, child in value.items()}
    if isinstance(value, list):
        return [_expand_constraint_references(child, profiles) for child in value]
    return copy.deepcopy(value)


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


@pytest.mark.parametrize("fn", [name for name, cap in CAPABILITY_REGISTRY.items() if cap.prompt_visible and cap.decision == "expose"])
def test_compact_provider_roundtrips_every_complete_capability_witness(fn):
    item = build_capability_witness(fn)
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
