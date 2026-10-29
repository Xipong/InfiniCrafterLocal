"""Lossless prompt metadata sharing and the real strict-provider inverse seam."""
from __future__ import annotations
from prompt_packet_helpers import request_dossier, dossier_text, expand_catalog_targets

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
                if key in {"consumerConstraint", "x-infini-consumerConstraint",
                           "projectionConstraints", "x-infini-authorProjection"} and isinstance(child, str)
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
        *parents, "lifetime-guidance", model_name="offline-readonly-context")
    assert request["response_format"]["type"] == mode
    assert dossier_text(request) == serialized
    packet = json.loads(serialized)
    spec = CAPABILITY_REGISTRY["set_projectile_lifetime"].params["lifetimeSeconds"]
    assert (spec.minimum, spec.maximum) == (spec.minimum, spec.maximum)
    bounds = {"minimum": spec.minimum, "maximum": spec.maximum}
    assert packet["balanceCorridor"]["broadEnvelope"]["lifetimeSeconds"] == bounds
    card = next(row for row in packet["runtimeCapabilityContract"]["catalog"]["capabilities"]
                if row["fn"] == "set_projectile_lifetime")
    assert (card["params"]['lifetimeSeconds']["min"], card["params"]['lifetimeSeconds']["max"]) == (spec.minimum, spec.maximum)

    item = build_runtime_fixture("workbench_blade")
    index, lifetime = next((index, row) for index, row in enumerate(item["runtimeProgram"]["calls"])
                           if row["fn"] == "set_projectile_lifetime")
    lifetime["params"]['lifetimeSeconds'] = (36000) / 60
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
        lifetime["params"]['lifetimeSeconds'] = (ticks) / 60
        retained = compile_runtime_program(item)
        retained_entity = next(row for row in retained["runtimeProgram"]["entities"]
                               if row["id"] == lifetime["target"])
        assert retained_entity["lifetimeTicks"] == ticks
        assert validate_runtime_wire(retained)["ok"]
    lifetime["params"]['lifetimeSeconds'] = (36000) / 60
    assert item == accepted_before

    lifetime["params"]['lifetimeSeconds'] = (36001) / 60
    assert not Draft202012Validator(local_schema).is_valid(item)
    provider_item["runtimeProgram"]["calls"][index]["params"]['lifetimeSeconds'] = (36001) / 60
    assert not Draft202012Validator(provider_schema).is_valid(provider_item)
    invalid_before = copy.deepcopy(item)
    failure = validate_runtime_program(item)
    path = f"$.runtimeProgram.calls[{index}].params.lifetimeSeconds"
    assert not failure["ok"]
    assert any(row["path"] == path and row["code"] == "shape_maximum"
               for row in failure["errors"]), failure
    with pytest.raises(ValueError):
        compile_runtime_program(item)
    entity["lifetimeTicks"] = 36001
    assert not validate_runtime_wire(wire)["ok"]
    with pytest.raises(_CapturedBeforeTransport):
        author.repair_author_item_after_failure(
            item, *parents, "lifetime-guidance", failure_report=failure)
    assert len(captured) == 1
    repair_request = captured[0]
    assert repair_request["response_format"]["type"] == mode
    repair = request_dossier(repair_request)
    repair_card = next(row for row in repair["existingBrokenCapabilityCards"]
                       if row["fn"] == "set_projectile_lifetime")
    assert (repair_card["params"]['lifetimeSeconds']["min"],
            repair_card["params"]['lifetimeSeconds']["max"]) == (spec.minimum, spec.maximum)
    assert repair["acceptedItemContext"]["runtimeProgram"] == item["runtimeProgram"]
    assert repair["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": lifetime["id"], "paths": ['params.lifetimeSeconds']}]
    assert item == invalid_before and parents == before

    # Syntax-only Repair preserves its exact malformed source, not a second
    # design dossier containing parents and balance instructions.
    with pytest.raises(_CapturedBeforeTransport):
        author._repair_malformed_author_json(
            malformed_raw_text=json.dumps(item)[:-1] + ",}", parse_error=ValueError("trailing comma"),
            original_recipe_context=serialized, model_name="offline-readonly-context")
    format_packet = request_dossier(captured[1])
    assert "originalRecipeContext" not in format_packet
    assert json.loads(format_packet["malformedRawText"][:-2] + "}") == item

    # A different declared maximum must reach the real packet, not a copied cap.
    cap = CAPABILITY_REGISTRY["set_projectile_lifetime"]
    changed = replace(cap, params={**cap.params, "lifetimeSeconds": replace(spec, maximum=350)})
    monkeypatch.setattr(balance, "CAPABILITY_REGISTRY", {**CAPABILITY_REGISTRY, cap.name: changed})
    variant_request, variant_serialized, _ = author.build_initial_author_request(
        *parents, "lifetime-guidance", model_name="offline-readonly-context")
    variant_packet = json.loads(variant_serialized)
    assert variant_packet["balanceCorridor"]["broadEnvelope"]["lifetimeSeconds"]["maximum"] == 350
    variant_packet["balanceCorridor"]["broadEnvelope"]["lifetimeSeconds"]["maximum"] = spec.maximum
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
    assert set(references) <= set(profiles)
    assert len(profiles) < len(references)
    assert originals == {name: cap.author_prompt_card() for name, cap in CAPABILITY_REGISTRY.items()}
    # Structured params use the same numeric guard as scalar params, not a
    # second literal copy hidden inside their schema annotations.
    nested_references = []

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"x-infini-consumerConstraint", "projectionConstraints", "x-infini-authorProjection"}:
                    assert isinstance(child, str)
                    nested_references.append(child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(catalog["capabilities"])
    assert nested_references and set(nested_references) <= set(profiles)
    assert set(references + nested_references) == set(profiles)
    expanded = _expand_constraint_references(catalog["capabilities"], profiles)
    expanded = expand_catalog_targets(expanded, catalog["fieldGuide"]["targetKindSets"])
    assert [{key: value for key, value in card.items() if key != "constructionMeaning"}
            for card in expanded] == [cap.author_prompt_card() for cap in CAPABILITY_REGISTRY.values()
                                      if cap.author_visible]
    # The double rule is retained separately; it is not recast as a float32 guard.
    doubles = [value for value in profiles.values() if value.get("storage") == "float64"]
    assert len(doubles) == 1 and doubles[0]["rule"] == "finite_double_no_normalization"


@pytest.mark.parametrize("field", ["consumerConstraint", "x-infini-consumerConstraint",
                                  "projectionConstraints", "x-infini-authorProjection"])
def test_new_constraint_metadata_gets_its_own_definition_without_profile_guessing(field):
    first = {"storage": "future_storage", "neutral": 7, "wireProjection": {"divisor": 37},
             "meaning": "A new literal rule which must not match an existing profile."}
    second = {**first, "neutral": 8}
    cards = [{"params": {"one": {field: copy.deepcopy(first)},
                          "two": {field: copy.deepcopy(first)},
                          "three": {"nested": {field: copy.deepcopy(second)}}}}]
    profiles = prompt._share_consumer_constraints(cards)
    params = cards[0]["params"]
    assert len(profiles) == 2
    assert params["one"][field] == params["two"][field]
    assert profiles[params["one"][field]] == first
    assert profiles[params["three"]["nested"][field]] == second


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
    pytest.param("spawn_entity_on_event", {"when": {"everySeconds": 0.5}}, None, id="event-object-branch"),
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
    assert {row["fn"] for row in prompt.sharp_engine_fn_catalog_for_llm()["capabilities"]} == {name for name, cap in CAPABILITY_REGISTRY.items() if cap.author_visible}


def test_author_card_compaction_keeps_every_constraint_and_consumer_description():
    """Only duplicated documentation may disappear; schema/operation facts stay exact."""
    seconds_primer = "World duration (seconds); shared nearest-tick rounding applies. Native consumer: "
    checked_descriptions = []
    omitted_root_copies = []
    guide = prompt.sharp_engine_fn_catalog_for_llm()["fieldGuide"]
    shared_types = guide["types"]
    checked_shared_types = set()

    def consumer_text(text, metadata):
        text = text.removeprefix(seconds_primer)
        units = metadata.get("units", metadata.get("x-infini-units"))
        return text.removeprefix(f"Author units: {units}. Native consumer: ") if units else text

    def comparison_metadata(card):
        result = copy.deepcopy({key: value for key, value in card.items() if key != "params"})
        rules = []
        for row in result.pop("requires", []):
            if row["kind"] == "present_param_forbids_capability":
                forbidden = CAPABILITY_REGISTRY.get(row.get("capability"))
                if forbidden is not None and not forbidden.author_visible:
                    continue
            elif row["kind"] == "capability_absent" and "anyOf" in row:
                row["anyOf"] = [fn for fn in row["anyOf"] if fn not in CAPABILITY_REGISTRY
                                or CAPABILITY_REGISTRY[fn].author_visible]
                if not row["anyOf"]:
                    continue
            rules.append({**guide["requirementNotation"]["omittedMetadata"], **row})
        if rules:
            result["requires"] = rules
        if result.get("effectGroups") == {"$ref": "#/fieldGuide/effectGroups"}:
            result["effectGroups"] = copy.deepcopy(guide["effectGroups"])
        return result

    def compare_shape(source, sent, path, root_meaning=None):
        if isinstance(source, dict):
            assert isinstance(sent, dict), path
            removed = set(source) - set(sent)
            assert not set(sent) - set(source), path
            if removed:
                # The exact text must still occur at its parameter or sole
                # branch property; no description may simply vanish.
                assert removed == {"description"}, path
                retained = root_meaning
                properties = sent.get("properties", {})
                if retained is None and len(properties) == 1:
                    retained = next(iter(properties.values())).get("description")
                assert retained is not None, path
                assert consumer_text(source["description"], source) == retained, path
                omitted_root_copies.append(path)
            for key in set(source) & set(sent):
                if key == "description" and isinstance(source[key], str):
                    assert sent[key] == consumer_text(source[key], source), path
                    checked_descriptions.append(path)
                else:
                    compare_shape(source[key], sent[key], path + "." + key)
        elif isinstance(source, list):
            assert isinstance(sent, list) and len(sent) == len(source), path
            for index, (before, after) in enumerate(zip(source, sent)):
                compare_shape(before, after, path + f"[{index}]")
        else:
            assert sent == source, path

    for name, cap in CAPABILITY_REGISTRY.items():
        if not cap.author_visible:
            continue  # Full machine/saved-wire coverage is not a fresh Author projection.
        raw = cap.prompt_card()
        sent = cap.author_prompt_card()
        assert comparison_metadata(raw) == comparison_metadata(sent)
        assert set(raw["params"]) == set(sent["params"])
        for param, source in raw["params"].items():
            target = sent["params"][param]
            if "paramRef" in target:
                owner, leaf = target["paramRef"].split(".")
                assert leaf == param and CAPABILITY_REGISTRY[owner].params[leaf] == cap.params[param]
                target = CAPABILITY_REGISTRY[owner].author_prompt_card()["params"][leaf]
                assert "paramRef" not in target
            spec = cap.params[param]
            if spec.shared_type:
                # Sharing replaces repeated metadata, not any branch, operator,
                # units, description or latch dependency of the source schema.
                expected: dict[str, object] = {"typeRef": spec.shared_type}
                if not spec.required:
                    expected["optional"] = True
                expected.update({key: source[key] for key in ("default", "neutral", "omissionAllowedOnlyWhen") if key in source})
                assert target == expected, (name, param)
                expanded_shape = copy.deepcopy(shared_types[spec.shared_type])
                if "default" in target:
                    expanded_shape["default"] = target["default"]
                if "neutral" in target:
                    expanded_shape["x-infini-neutral"] = target["neutral"]
                assert expanded_shape == source["shape"] == spec.schema()
                assert source["meaning"] == shared_types[spec.shared_type]["description"]
                checked_shared_types.add(spec.shared_type)
                continue
            # Previously documented card notation controls these presentation
            # columns; all actual domain/reference/storage/projection rules remain.
            for key in source.keys() - {"meaning", "required", "semanticType", "neutral", "units", "shape"}:
                assert target[key] == source[key], (name, param, key)
            meaning = consumer_text(source["meaning"], source)
            if name == "configure_armor" and "meaning" not in target:
                # Armor borrows only an identical accessory effect description.
                assert CAPABILITY_REGISTRY["configure_accessory"].params[param].description == spec.description
                assert CAPABILITY_REGISTRY["configure_accessory"].author_prompt_card()["params"][param]["meaning"] == meaning
            else:
                if name == "configure_armor" and param.startswith("setBonus"):
                    meaning = meaning.removeprefix("Matching armor set (head piece only; matching head, body and legs must actually be equipped): ")
                assert target["meaning"] == meaning, (name, param)
            checked_descriptions.append(name + "." + param)
            if "units" in source:
                if "units" in target:
                    assert target["units"] == source["units"], (name, param)
                else:
                    assert any(param.endswith(suffix) and source["units"] == units
                               for suffix, units in (("Seconds", "seconds"), ("Tiles", "blocks (tiles)"),
                                                     ("Px", "pixels"), ("Radians", "radians"))), (name, param)
            assert target.get("optional", False) is not spec.required
            if "neutral" in source and "neutral" not in target:
                assert not spec.required and source["neutral"] == 0, (name, param)
            elif "neutral" in source:
                assert target["neutral"] == source["neutral"], (name, param)
            if "shape" in source:
                compare_shape(source["shape"], target["shape"], name + "." + param,
                              root_meaning=target.get("meaning"))
    assert checked_descriptions and omitted_root_copies
    assert checked_shared_types == set(shared_types)
