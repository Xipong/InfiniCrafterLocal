"""Request-local Repair grammar must preserve scope, inverses and exact sources."""
from __future__ import annotations

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    filter_repair_patch_scope, validate_runtime_program,
)
from infini_local.core.runtime_authoring.repair_scope import runtime_repair_schema_capabilities
from infini_local.pipelines import author_item_contract as contract
from infini_local.pipelines import llm_authoring_pipeline as author, llm_transport as transport
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_codex_subscription_contract import _encode_nullable_fixture
from test_gameplay_repair_readonly_context import _offline_builder


def _local(scope):
    return contract.author_item_repair_response_schema(capability_names=runtime_repair_schema_capabilities(scope))


def _call(item, fn):
    return next(row for row in item["runtimeProgram"]["calls"] if row["fn"] == fn)


def _wire_roundtrip(patch, local):
    provider = contract.author_item_provider_repair_response_schema(local_schema=local)
    encoded = _encode_nullable_fixture(patch, local)
    Draft202012Validator(provider).validate(encoded)
    restored = contract.project_provider_nullable_optionals_to_local(
        encoded, local_schema=local,
        response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert restored == patch
    return provider, encoded


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_parameter_repair_uses_exact_scoped_schema_and_retains_accepted_omission(monkeypatch, mode):
    item = build_runtime_fixture("workbench_blade")
    stats = _call(item, "configure_item_stats")
    stats["params"].pop("manaCost")
    expected = copy.deepcopy(item)
    stats["params"]["damage"] = -1
    failure = validate_runtime_program(item)
    scope = build_runtime_repair_scope(item, failure["errors"])
    assert runtime_repair_schema_capabilities(scope) == ["configure_item_stats"]
    local = _local(scope)
    fixed = copy.deepcopy(_call(expected, "configure_item_stats"))
    patch = {"note": "Repair exact damage only", "callsUpsert": [fixed], "realizationReplacement": item["realization"]}
    provider, encoded = _wire_roundtrip(patch, local)
    requests = []

    def respond(request, **_kwargs):
        requests.append(copy.deepcopy(request))
        if mode == "json_schema":
            assert request["response_format"]["json_schema"]["schema"] == provider
            assert encoded["callsUpsert"][0]["params"]["manaCost"] is None
        return {"choices": [{"message": {"content": json.dumps(encoded if mode == "json_schema" else patch)}}],
                "_debug": {"responseFormatType": mode}}

    _offline_builder(monkeypatch, mode, respond)
    before = copy.deepcopy(item)
    repaired = author.repair_author_item_after_failure(item, {}, {}, {}, {}, "scoped-request", failure_report=failure)
    assert len(requests) == 1
    assert repaired["debug"]["gameplayRepairScope"] == scope
    repaired.pop("debug")
    assert repaired == expected and item == before
    assert "manaCost" not in _call(repaired, "configure_item_stats")["params"]


def test_single_function_schema_never_decodes_an_unknown_function_by_object_type():
    local = contract.author_item_repair_response_schema(capability_names=["configure_item_stats"])
    provider = contract.author_item_provider_repair_response_schema(local_schema=local)
    bad = {"note": "unknown function", "callsUpsert": [{"id": "probe", "fn": "not_registered", "target": "item", "params": {"manaCost": None}}]}
    actual = contract.project_provider_nullable_optionals_to_local(
        bad, local_schema=local, response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert actual == bad
    assert not Draft202012Validator(provider).is_valid(bad)


@pytest.mark.parametrize("scope", [
    {"identityChanges": {"callFnIds": ["move"]}},
    {"fieldPermissions": {"calls": [{"id": "move", "paths": ["fn"]}]}},
    {"fieldPermissions": {"calls": [{"id": "move", "paths": [""]}]}},
])
def test_authorized_function_or_whole_call_edits_keep_every_registered_variant(scope):
    assert set(runtime_repair_schema_capabilities(scope)) == {name for name, cap in CAPABILITY_REGISTRY.items() if cap.prompt_visible}


def test_empty_scope_never_becomes_full_catalog_and_unknown_names_fail_closed():
    assert runtime_repair_schema_capabilities({}) == []
    local = _local({})
    assert local["properties"]["callsUpsert"]["maxItems"] == 0
    assert contract.author_item_repair_prompt_shape_card(capability_names=[])["callsUpsert"] == []
    for rows, valid in [([], True), ([{"id": "illegal"}], False)]:
        patch = {"note": "no call changes", "callsUpsert": rows}
        assert Draft202012Validator(local).is_valid(patch) is valid
    _wire_roundtrip({"note": "empty call list", "callsUpsert": []}, local)
    with pytest.raises(ValueError, match="non-public"):
        runtime_repair_schema_capabilities({"capabilitySubset": ["not_registered"]})
    with pytest.raises(ValueError, match="Unknown"):
        contract.author_item_repair_response_schema(capability_names=["not_registered"])


def test_create_policy_and_event_support_are_included_without_granting_permissions():
    item = build_runtime_fixture("door_on_chain")
    damage = copy.deepcopy(_call(item, "set_projectile_damage"))
    item["runtimeProgram"]["calls"].remove(_call(item, "set_projectile_damage"))
    event = _call(item, "apply_status_on_event")
    event["params"]["when"] = "on_spawn"
    failure = validate_runtime_program(item)
    scope = build_runtime_repair_scope(item, failure["errors"])
    before = copy.deepcopy(scope)
    assert "set_projectile_damage" in runtime_repair_schema_capabilities(scope)
    assert "apply_status_on_event" in runtime_repair_schema_capabilities(scope)
    corrected = copy.deepcopy(event)
    corrected["params"]["when"] = "on_hit"
    patch = {"note": "Explicit event and its exact producer", "callsUpsert": [corrected, damage],
             "realizationReplacement": item["realization"]}
    _wire_roundtrip(patch, _local(scope))
    filtered, audit = filter_repair_patch_scope(item, patch, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(item, filtered))["ok"]
    assert scope == before
    # Missing-component create alternatives remain a complete finite set.
    missing = build_runtime_fixture("workbench_blade")
    missing["runtimeProgram"]["calls"].remove(_call(missing, "move_forward_then_retract"))
    create_scope = build_runtime_repair_scope(missing, validate_runtime_program(missing)["errors"])
    assert create_scope["create"]["calls"]["allowed"]
    assert set(create_scope["create"]["calls"]["allowedFns"]) <= set(runtime_repair_schema_capabilities(create_scope))


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("rewrite", [False, True])
def test_format_repair_keeps_exact_dynamic_facts_and_rejects_gameplay_rewriting(monkeypatch, mode, rewrite):
    item = build_runtime_fixture("workbench_blade")
    item["concept"]["literalSynthesis"] = "  Exact source 雪\r\n without trimming  "
    raw = json.dumps(item, ensure_ascii=False)[:-1] + ",}"
    original = {key: {"staticMarker": key} for key in author._AUTHOR_CACHE_PREFIX_KEYS}
    original.update(recipeKey="format-only", parents={"A": {"raw": {"value": 0.14700000000000002}}},
                    balanceCorridor={"exact": None}, futureRecipeFact={"mustSurvive": False})
    expected_context = {key: value for key, value in original.items() if key not in author._AUTHOR_CACHE_PREFIX_KEYS}
    response = copy.deepcopy(item)
    if rewrite:
        _call(response, "configure_item_stats")["params"]["damage"] += 1
    requests = []

    def respond(request, **_kwargs):
        requests.append(copy.deepcopy(request))
        payload = _encode_nullable_fixture(response, contract.author_item_response_schema()) if mode == "json_schema" else response
        return {"choices": [{"message": {"content": json.dumps(payload)}}], "_debug": {"responseFormatType": mode}}

    _offline_builder(monkeypatch, mode, respond)
    call = lambda: author._repair_malformed_author_json(
        malformed_raw_text=raw, parse_error=ValueError("trailing comma"),
        original_recipe_context=json.dumps(original, ensure_ascii=False), model_name="offline-format")
    if rewrite:
        with pytest.raises(PlannerUnavailable, match="changed recoverable authored fields"):
            call()
    else:
        repaired, _ = call()
        assert repaired == item
    assert len(requests) == 1
    packet = json.loads(requests[0]["messages"][1]["content"])
    assert packet["originalRecipeContext"] == expected_context
    assert packet["malformedRawText"] == raw
    assert packet["requiredJsonShape"] == contract.author_item_prompt_shape_card()
    assert set(packet["allowedCallParamsReadOnly"]) == {name for name, cap in CAPABILITY_REGISTRY.items() if cap.prompt_visible}
