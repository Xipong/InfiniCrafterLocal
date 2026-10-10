"""Typed alternatives require a proof before provider oneOf -> anyOf projection."""
from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring import capability_registry as registry
from infini_local.core.runtime_authoring.capability_registry import ParamSpec
from infini_local.pipelines import author_item_contract as contract
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_codex_subscription_contract import _encode_nullable_fixture


def _object(**fields):
    return ParamSpec("object", "Explicit test choice", properties={**fields, "delayTicks": ParamSpec("integer", "Explicit test choice", required=False, minimum=0)})


CONDITIONS = ParamSpec("union", "Explicit test choice", alternatives=(
    ParamSpec("string", "Explicit test choice", enum=("grounded", "not_wet")),
    _object(lifeAtLeast=ParamSpec("integer", "Explicit test choice", minimum=1)),
    _object(manaAtLeast=ParamSpec("integer", "Explicit test choice", minimum=1)),
))
SPAWNS = ParamSpec("union", "Explicit test choice", alternatives=(
    _object(at=ParamSpec("string", "Explicit test choice", enum=("player", "cursor"))),
    _object(above=ParamSpec("string", "Explicit test choice", enum=("player", "cursor")), heightTiles=ParamSpec("number", "Explicit test choice", minimum=0)),
))
IMMUNITY = ParamSpec("union", "Explicit test choice", alternatives=(
    ParamSpec("string", "Explicit test choice", enum=("owner", "once_per_projectile")),
    _object(localCooldown=ParamSpec("integer", "Explicit test choice", minimum=1)),
))
WHEN = ParamSpec("union", "Explicit test choice", alternatives=(
    ParamSpec("string", "Explicit test choice", enum=("on_use", "on_hit")),
    _object(everyTicks=ParamSpec("integer", "Explicit test choice", minimum=1)),
))


def _schema(spec):
    return {"type": "object", "additionalProperties": False, "required": ["choice"],
            "properties": {"choice": spec.schema(), "tail": {"type": "integer"}}}


def _inverse(value, local, provider):
    return contract.project_provider_nullable_optionals_to_local(
        value, local, response_format={"type": "json_schema", "json_schema": {"schema": provider}})


@pytest.mark.parametrize("spec,value", [
    (CONDITIONS, "grounded"), (CONDITIONS, "not_wet"),
    (CONDITIONS, {"lifeAtLeast": 10}), (CONDITIONS, {"manaAtLeast": 20, "delayTicks": 0}),
    (SPAWNS, {"at": "cursor"}), (SPAWNS, {"above": "player", "heightTiles": 12.5}),
    (IMMUNITY, "owner"), (IMMUNITY, {"localCooldown": 3}),
    (WHEN, "on_hit"), (WHEN, {"everyTicks": 30}),
])
def test_canonical_typed_alternatives_roundtrip_without_defaults(spec, value):
    local = _schema(spec)
    before = copy.deepcopy(local)
    provider = contract._provider_strict_projection(local)
    authored = {"choice": value}
    assert Draft202012Validator(local).is_valid(authored)
    encoded = _encode_nullable_fixture(authored, local)
    assert Draft202012Validator(provider).is_valid(encoded)
    assert _inverse(encoded, local, provider) == authored
    assert local == before


@pytest.mark.parametrize("value", [
    None, True, 1, "unknown", {}, {"unknown": None},
    {"at": "cursor", "above": "cursor", "heightTiles": 1, "delayTicks": None},
    {"above": "cursor", "delayTicks": None},
    {"above": "cursor", "heightTiles": None, "delayTicks": None},
    {"at": None, "delayTicks": None},
    {"at": "cursor", "unknown": None, "delayTicks": None},
])
def test_unknown_missing_null_and_conflicting_choices_stay_invalid(value):
    local = _schema(SPAWNS)
    provider = contract._provider_strict_projection(local)
    encoded = {"choice": value, "tail": None}
    before = copy.deepcopy(encoded)
    assert not Draft202012Validator(provider).is_valid(encoded)
    restored = _inverse(encoded, local, provider)
    assert not Draft202012Validator(local).is_valid(restored)
    assert encoded == before
    # Unknown keys are never nullable transport aliases.
    if isinstance(value, dict) and "unknown" in value:
        assert restored["choice"]["unknown"] is None
    if isinstance(value, dict) and "heightTiles" in value and value["heightTiles"] is None:
        assert restored["choice"]["heightTiles"] is None


def test_structural_choice_keeps_invalid_neighbour_for_repair_without_validating_whole_branch():
    local = _schema(SPAWNS)
    provider = contract._provider_strict_projection(local)
    encoded = {"choice": {"above": "cursor", "heightTiles": "invalid", "delayTicks": None}, "tail": None}
    restored = _inverse(encoded, local, provider)
    assert restored == {"choice": {"above": "cursor", "heightTiles": "invalid"}}
    assert not Draft202012Validator(local).is_valid(restored)


def _closed(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required,
            "additionalProperties": False}


def test_each_pair_can_have_a_different_proven_discriminator():
    branches = [
        _closed({"a": {"const": "x"}}),
        _closed({"a": {"const": "y"}, "b": {"const": "p"}}),
        _closed({"b": {"const": "q"}}),
    ]
    assert contract._union_discriminator_paths(branches) == []
    local = {"oneOf": branches}
    provider = contract._provider_strict_projection(local)
    for value in ({"a": "x"}, {"a": "y", "b": "p"}, {"b": "q"}, {}, {"a": "y"}, {"a": "x", "b": "q"}):
        assert Draft202012Validator(local).is_valid(value) == Draft202012Validator(provider).is_valid(value)
    assert provider["anyOf"] == [contract._provider_strict_projection(branch) for branch in branches]


@pytest.mark.parametrize("branches", [
    [{"type": "integer"}, {"type": "number"}],
    [{"enum": [1]}, {"enum": [1.0]}],
    [_closed({"a": {"type": "integer"}}, []), _closed({"b": {"type": "integer"}}, [])],
    [{"type": "string"}, _closed({"a": {"type": "integer"}}), {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}],
    [{"type": "object", "properties": {"a": {}}, "required": ["a"]},
     {**_closed({"b": {}}, ["b"]), "patternProperties": {"^a$": {}}}],
    [_closed({"nested": _closed({"a": {"const": "x"}})}, []),
     _closed({"nested": _closed({"a": {"const": "y"}})}, [])],
])
def test_one_overlapping_or_unproved_pair_rejects_the_entire_projection(branches):
    local = {"oneOf": branches}
    before = copy.deepcopy(local)
    with pytest.raises(ValueError, match="Unproved provider oneOf"):
        contract._provider_strict_projection(local)
    assert local == before


def test_nested_closed_keys_require_every_ancestor_and_keep_json_boolean_numeric_distinction():
    local = {"oneOf": [_closed({"nested": _closed({name: {"type": "integer"}})}) for name in ("a", "b")]}
    provider = contract._provider_strict_projection(local)
    for value in ({"nested": {"a": 1}}, {"nested": {"b": 2}}, {"nested": {}}, {}):
        assert Draft202012Validator(local).is_valid(value) == Draft202012Validator(provider).is_valid(value)
    scalar = {"oneOf": [{"enum": [True]}, {"enum": [1]}]}
    projected = contract._provider_strict_projection(scalar)
    for value in (True, False, 1, 1.0, 0):
        assert Draft202012Validator(scalar).is_valid(value) == Draft202012Validator(projected).is_valid(value)


def test_scoped_singleton_does_not_decode_unknown_function_by_object_type():
    local = {"oneOf": [_closed({"fn": {"const": "registered"}, "optional": {"type": "integer"}}, ["fn"])]}
    provider = contract._provider_strict_projection(local)
    assert _inverse({"fn": "registered", "optional": None}, local, provider) == {"fn": "registered"}
    unknown = {"fn": "unknown", "optional": None}
    assert _inverse(unknown, local, provider) == unknown


@pytest.mark.parametrize("value", ["grounded", {"lifeAtLeast": 10}, {"manaAtLeast": 20}])
def test_typed_registry_schema_reaches_actual_author_request_and_repair_inverse(monkeypatch, value):
    item = build_runtime_fixture("workbench_blade")
    original = registry.CAPABILITY_REGISTRY["configure_item_stats"]
    changed = replace(original, params={**original.params, "proofChoice": CONDITIONS})
    monkeypatch.setattr(registry, "CAPABILITY_REGISTRY", {**registry.CAPABILITY_REGISTRY, original.name: changed})
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_schema")
    call = next(row for row in item["runtimeProgram"]["calls"] if row["fn"] == original.name)
    call["params"]["proofChoice"] = value
    request, text, _ = build_initial_author_request({}, {}, {}, {}, "offline-union-proof", model_name="offline")
    assert json.loads(text)["recipeKey"] == "offline-union-proof"
    local = contract.author_item_response_schema()
    encoded = _encode_nullable_fixture(item, local)
    Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(encoded)
    assert contract.project_provider_author_item_to_local(encoded, response_format=request["response_format"]) == item
    repair = {"note": "Explicit registered union", "callsUpsert": [call]}
    repair_local = contract.author_item_repair_response_schema()
    repair_provider = contract.author_item_provider_repair_response_schema()
    encoded_repair = _encode_nullable_fixture(repair, repair_local)
    Draft202012Validator(repair_provider).validate(encoded_repair)
    assert _inverse(encoded_repair, repair_local, repair_provider) == repair
