"""Exact redundant binding literals preserve mechanics and source presence."""
from copy import deepcopy
import json

import pytest

from infini_local.core.runtime_authoring import (
    compile_runtime_program, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.binding_use_policy import action_kind
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _binding_case(case):
    if case == "equipped":
        doc = build_capability_witness("configure_accessory")
    elif case == "effects":
        doc = build_capability_witness("move_player_on_use")
    elif case == "body":
        doc = build_capability_witness("configure_item_use")
    elif case == "hold":
        doc = build_runtime_fixture("held_and_deployed")
        row = doc["runtimeProgram"]["bindings"][0]
        row["input"] = "hold"
        row["action"].pop("kind")
        row.pop("stackCost")
        row.pop("contactDamage")
    else:
        doc = build_runtime_fixture("fishing_platform_tool")
    row = next(row for row in doc["runtimeProgram"]["bindings"]
               if (row["input"] == case if case in {"equipped", "hold"}
                   else action_kind(row) == {"body": "use_item_body", "effects": "apply_item_effects",
                                             "placement": "place_item"}[case]))
    return doc, row


def _explicit(doc, row):
    result = deepcopy(row)
    kind = action_kind(row)
    result.setdefault("action", {})["kind"] = kind
    if kind != "spawn_entity":
        result["action"]["targetId"] = next(e["id"] for e in doc["runtimeProgram"]["entities"]
                                             if e["kind"] == "item_body")
    if row["input"] in {"equipped", "hold"} or kind == "place_item":
        result.update(stackCost=1 if kind == "place_item" else 0, contactDamage=False)
    return result


@pytest.mark.parametrize("contact_damage", [False, True], ids=["mining-only", "mining-and-contact"])
def test_primary_body_tool_admission_preserves_independent_contact_lane(contact_damage):
    doc = build_capability_witness("configure_tool")
    doc["runtimeProgram"]["bindings"][0]["contactDamage"] = contact_damage
    before = json.dumps(doc, sort_keys=True)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    final = _assert_delivery(doc)
    assert final["runtimeProgram"]["bindings"][0]["usePolicy"]["contactDamage"] is contact_damage
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("root", ["body", "spawn"])
@pytest.mark.parametrize("contact_damage", [False, True])
def test_native_tool_stats_are_identical_across_independent_primary_contact(root, contact_damage):
    doc = build_capability_witness("configure_tool") if root == "body" else build_runtime_fixture("workbench_blade")
    if root == "spawn":
        doc["runtimeProgram"]["calls"].append({"id": "native_tool", "fn": "configure_tool", "params": {
            "pickPower": 190, "axePowerTooltipPercent": 45, "hammerPower": 20, "miningSpeedMultiplier": 0.75}})
    else:
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_tool")["params"] = {
            "pickPower": 190, "axePowerTooltipPercent": 45, "hammerPower": 20, "miningSpeedMultiplier": 0.75}
    doc["runtimeProgram"]["bindings"][0]["contactDamage"] = contact_damage
    final = _assert_delivery(doc)
    assert {key: final["gameplay"][key] for key in ("pickPower", "axePower", "hammerPower", "miningSpeedScale")} == {
        "pickPower": 190, "axePower": 9, "hammerPower": 20, "miningSpeedScale": 0.75}
    assert final["runtimeProgram"]["bindings"][0]["usePolicy"]["contactDamage"] is contact_damage


@pytest.mark.parametrize("case", ["alternate-only", "equipped-only", "effects-primary", "placement-primary", "missing-item-use"])
def test_native_tool_requires_legitimate_primary_root_not_arbitrary_binding(case):
    doc = build_capability_witness("configure_tool")
    row = doc["runtimeProgram"]["bindings"][0]
    if case == "alternate-only":
        row["input"] = "alternate_use"
    elif case == "equipped-only":
        row.update(input="equipped", action={"kind": "equip_passive"})
        row.pop("stackCost")
        row.pop("contactDamage")
        doc["runtimeProgram"]["calls"].append({"id": "equipped", "fn": "configure_accessory", "params": {"defensePoints": 1}})
    elif case == "effects-primary":
        row["action"] = {"kind": "apply_item_effects"}
        doc["runtimeProgram"]["calls"].append({"id": "utility", "fn": "restore_resources_on_use", "params": {
            "healLife": 1, "healMana": 0, "usesPotionRules": False}})
    elif case == "placement-primary":
        row.update(action={"kind": "place_item", "placementCallId": "placement"}, stackCost=1, contactDamage=False)
        doc["runtimeProgram"]["calls"].append({"id": "placement", "fn": "configure_tile_placement", "params": {"tileId": 1, "placeStyle": 0}})
    else:
        doc["runtimeProgram"]["calls"] = [c for c in doc["runtimeProgram"]["calls"] if c["fn"] != "configure_item_use"]
    before = json.dumps(doc, sort_keys=True)
    report = validate_runtime_program(doc)
    tool_index = next(i for i, c in enumerate(doc["runtimeProgram"]["calls"]) if c["fn"] == "configure_tool")
    code = "missing_capability_dependency" if case == "missing-item-use" else "missing_binding_dependency"
    assert [e["code"] for e in report["errors"]] == ([code, "binding_dependency"] if case == "missing-item-use" else [code])
    assert any(e["code"] == code and e["path"] == f"$.runtimeProgram.calls[{tool_index}]" for e in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_noncontact_tool_unrelated_repair_keeps_binding_and_tool_stats_frozen(monkeypatch, format_mode):
    from infini_local.core.errors import PlannerUnavailable
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = build_capability_witness("configure_tool")
    row = doc["runtimeProgram"]["bindings"][0]
    row["contactDamage"] = False
    expected = deepcopy(doc)
    stats = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")
    stats["params"]["damage"] = True
    before = json.dumps(doc, sort_keys=True)
    noop = {"note": "no-op cannot repair unrelated invalid damage", "realizationReplacement": doc["realization"]}
    with pytest.raises(PlannerUnavailable):
        _offline_gameplay_repair(monkeypatch, doc, noop, format_mode)
    correction = deepcopy(stats)
    correction["params"]["damage"] = next(c for c in expected["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")["params"]["damage"]
    hostile = deepcopy(row)
    hostile.update(stackCost=1, contactDamage=True, action={"kind": "apply_item_effects", "targetId": "foreign_body"})
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "damage exact leaf only; contact/action/cost/target frozen", "realizationReplacement": doc["realization"],
        "callsUpsert": [correction], "bindingsUpsert": [hostile],
    }, format_mode)
    scope = dossier["repairScope"]
    assert scope["fieldPermissions"]["calls"] == [{"id": stats["id"], "paths": ["params.damage"]}]
    assert scope["fieldPermissions"]["bindings"] == []
    assert all(not values for values in scope["identityChanges"].values())
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert _assert_delivery(repaired) == _assert_delivery(expected)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_valid_noncontact_tool_noop_repair_preserves_complete_source(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = build_capability_witness("configure_tool")
    doc["runtimeProgram"]["bindings"][0]["contactDamage"] = False
    before = json.dumps(doc, sort_keys=True)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "valid native mining needs no contact correction", "realizationReplacement": doc["realization"],
    }, format_mode)
    assert dossier["exactValidationErrors"] == []
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == []
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == before
    _assert_delivery(repaired)


def _assert_delivery(doc):
    final = compile_runtime_program(doc)
    assert validate_runtime_wire(final)["ok"]
    assert audit_compiler_receipts(final["runtimeContract"]["finalWireReceipts"],
                                   authored_document=doc, final_document=final)["ok"]
    return final


@pytest.mark.parametrize("case", ["equipped", "hold", "body", "effects", "placement"])
def test_fixed_explicit_binding_envelope_has_exact_sparse_effect_parity(case):
    sparse, row = _binding_case(case)
    explicit = deepcopy(sparse)
    explicit["runtimeProgram"]["bindings"][sparse["runtimeProgram"]["bindings"].index(row)] = _explicit(sparse, row)
    before = json.dumps(explicit, sort_keys=True)
    assert validate_runtime_program(sparse)["ok"]
    assert validate_runtime_program(explicit)["ok"]
    sparse_final, explicit_final = _assert_delivery(sparse), _assert_delivery(explicit)
    # Provenance legitimately differs: explicit leaves cite their literal source.
    sparse_final.pop("runtimeContract")
    explicit_final.pop("runtimeContract")
    assert json.dumps(explicit_final, sort_keys=True) == json.dumps(sparse_final, sort_keys=True)
    assert json.dumps(explicit, sort_keys=True) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("case", ["equipped", "hold", "body", "effects", "placement"])
@pytest.mark.parametrize("explicit", [False, True], ids=["sparse", "explicit"])
def test_binding_input_leaf_repair_preserves_exact_envelope(monkeypatch, format_mode, case, explicit):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case(case)
    if explicit:
        row.update(_explicit(doc, row))
    expected = deepcopy(doc)
    before = json.dumps(doc, sort_keys=True)
    selected_input = row["input"]
    row["input"] = "not_an_input"
    candidate = deepcopy(row)
    candidate["input"] = selected_input
    if explicit:
        if case in {"equipped", "hold"}:
            candidate["action"].pop("kind")
        if case != "hold":
            candidate["action"].pop("targetId")
        if case in {"equipped", "hold", "placement"}:
            candidate.pop("stackCost")
            candidate.pop("contactDamage")
        if not candidate["action"]:
            candidate.pop("action")
    else:
        candidate = _explicit(doc, candidate)
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "exact input correction", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [candidate],
    }, format_mode)
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == before
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_missing_effects_binding_creation_accepts_explicit_fixed_transaction(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("effects")
    candidate = _explicit(doc, row)
    expected = deepcopy(doc)
    expected["runtimeProgram"]["bindings"] = [candidate]
    assert validate_runtime_program(expected)["ok"]
    doc["runtimeProgram"]["bindings"] = []
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "exact required effects root", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [candidate],
    }, format_mode)
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("case,leaf,value", [
    pytest.param("equipped", "kind", "spawn_entity", id="wrong-equip-action"),
    pytest.param("hold", "kind", "equip_passive", id="wrong-hold-action"),
    pytest.param("equipped", "targetId", "missing", id="foreign-body-id"),
    pytest.param("equipped", "targetId", None, id="null-target"),
    pytest.param("equipped", "stackCost", 1, id="passive-cost-choice-forbidden"),
    pytest.param("placement", "stackCost", 0, id="placement-escrow-required"),
    pytest.param("placement", "contactDamage", True, id="placement-contact-forbidden"),
    pytest.param("equipped", "stackCost", False, id="boolean-not-zero"),
    pytest.param("equipped", "stackCost", 0.0, id="float-not-integer"),
    pytest.param("hold", "contactDamage", 0, id="integer-not-false"),
])
def test_invalid_fixed_literal_never_collapses_into_sparse_admission(case, leaf, value):
    from infini_local.core.runtime_authoring.binding_use_policy import transaction_key

    doc, row = _binding_case(case)
    candidate = _explicit(doc, row)
    canonical = transaction_key(row, item_body_id="item")
    (candidate["action"] if leaf in {"kind", "targetId"} else candidate)[leaf] = value
    row.update(candidate)
    before = json.dumps(doc, sort_keys=True)
    assert not validate_runtime_program(doc)["ok"]
    assert transaction_key(candidate, item_body_id="item") != canonical
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("case", ["equipped", "body", "effects", "placement"])
def test_explicit_body_owner_is_exact_arbitrary_declared_id_and_source_authenticated(case):
    doc, row = _binding_case(case)
    doc["runtimeProgram"]["entities"][0]["id"] = "opaque_body"
    if doc["runtimeProgram"]["primaryEntityId"] == "item":
        doc["runtimeProgram"]["primaryEntityId"] = "opaque_body"
    row.update(_explicit(doc, row))
    final = _assert_delivery(doc)
    forged = deepcopy(doc)
    forged["runtimeProgram"]["bindings"][doc["runtimeProgram"]["bindings"].index(row)]["action"]["targetId"] = "item"
    audit = audit_compiler_receipts(final["runtimeContract"]["finalWireReceipts"],
                                   authored_document=forged, final_document=final)
    assert not audit["ok"]
    assert any("binding" in json.dumps(error).lower() for error in audit["violations"])


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("case", ["equipped", "hold", "body", "effects", "placement"])
@pytest.mark.parametrize("explicit", [False, True], ids=["sparse", "explicit"])
def test_unrelated_repair_freezes_fixed_literal_presence_and_choices(monkeypatch, format_mode, case, explicit):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case(case)
    sparse_row = deepcopy(row)
    explicit_row = _explicit(doc, row)
    if explicit:
        row.update(explicit_row)
    expected_binding = deepcopy(row)
    stats = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")
    damage = stats["params"]["damage"]
    stats["params"]["damage"] = True
    correction = deepcopy(stats)
    correction["params"]["damage"] = damage
    hostile = sparse_row if explicit else explicit_row
    if case in {"body", "effects"}:
        hostile.update(stackCost=1, contactDamage=not row["contactDamage"])
        hostile["action"]["kind"] = "apply_item_effects" if case == "body" else "use_item_body"
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "damage correction with frozen binding rewrite", "realizationReplacement": doc["realization"],
        "callsUpsert": [correction], "bindingsUpsert": [hostile],
    }, format_mode)
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert next(b for b in repaired["runtimeProgram"]["bindings"] if b["id"] == row["id"]) == expected_binding
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_fixed_literal_type_repair_retains_other_exact_lanes(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("equipped")
    row.update(_explicit(doc, row))
    expected = deepcopy(doc)
    row["stackCost"] = False
    correction = deepcopy(row)
    correction["stackCost"] = 0
    correction["action"]["targetId"] = "foreign_body"
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "literal integer correction only", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [correction],
    }, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == [{"id": row["id"], "paths": ["stackCost"]}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_actual_author_packet_explains_uniform_binding_and_keeps_sparse_valid(monkeypatch, format_mode):
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines import llm_transport as transport

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    request, user, _ = author.build_initial_author_request({}, {}, {}, {}, "fixed-binding-proof", model_name="offline")
    assert request["messages"][1]["content"] == user
    assert "Fixed binding literals may be explicit or omitted" in user
    cards = json.loads(user)["requiredJsonShape"]["runtimeProgram"]["bindings"]
    assert all({"id", "input", "action", "stackCost", "contactDamage"} <= set(card) for card in cards)
    assert all({"kind", "targetId"} <= set(card["action"]) for card in cards)
    guide = json.loads(user)["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["bindingTarget"]
    assert "omit fixed contactDamage for place_item/hold/equipped" not in guide
    assert "Omit action.targetId for item_body-only actions" not in guide
    assert "fixed contactDamage=false for place_item/hold/equipped may be explicit or omitted" in guide
    assert "action.targetId for item_body-only actions may be explicit with the exact unique declared item_body id or omitted" in guide


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("case", ["equipped", "hold", "body", "effects", "placement"])
@pytest.mark.parametrize("explicit", [False, True], ids=["sparse", "explicit"])
def test_actual_author_preparation_roundtrip_preserves_binding_source(monkeypatch, format_mode, case, explicit):
    from jsonschema import Draft202012Validator
    from test_codex_subscription_contract import _encode_nullable_fixture
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines import llm_transport as transport
    from infini_local.pipelines.author_item_contract import author_item_response_schema

    doc, row = _binding_case(case)
    if explicit:
        row.update(_explicit(doc, row))
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    request, _, _ = author.build_initial_author_request({}, {}, {}, {}, "fixed-binding-wire", model_name="offline")
    payload = deepcopy(doc)
    if format_mode == "json_schema":
        payload = _encode_nullable_fixture(doc, author_item_response_schema())
        Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(payload)
    source = author._prepare_parsed_author_item(json.loads(json.dumps(payload)), response_format=request["response_format"])
    assert json.dumps(source, sort_keys=True) == json.dumps(doc, sort_keys=True)
    _assert_delivery(source)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("leaf,old,new", [
    ("kind", "spawn_entity", "equip_passive"),
    ("targetId", "foreign_body", "item"),
    ("stackCost", 1, 0),
    ("contactDamage", True, False),
])
def test_fixed_binding_wrong_present_leaf_requires_exact_explicit_repair(monkeypatch, format_mode, leaf, old, new):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("equipped")
    row.update(_explicit(doc, row))
    expected = deepcopy(doc)
    (row["action"] if leaf in {"kind", "targetId"} else row)[leaf] = old
    correction = deepcopy(row)
    (correction["action"] if leaf in {"kind", "targetId"} else correction)[leaf] = new
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "exact fixed leaf", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [correction],
    }, format_mode)
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_explicit_effect_group_and_probability_remain_frozen_independent_lanes(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("effects")
    effects = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "move_player_on_use")
    effects["params"]["effectGroupId"] = "chosen_group"
    row.update(_explicit(doc, row))
    row["action"]["effectGroupId"] = "chosen_group"
    row.update(stackCost=1, stackConsumeChancePercent=35)
    assert validate_runtime_program(doc)["ok"]
    expected = deepcopy(doc)
    row["input"] = "not_an_input"
    correction = deepcopy(row)
    correction["input"] = "primary_use"
    correction["action"]["effectGroupId"] = "other_group"
    correction["stackConsumeChancePercent"] = 99
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "input only, group/chance frozen", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [correction],
    }, format_mode)
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("body_id", ["item", "opaque_body"])
def test_empty_action_input_repair_preserves_frozen_source_through_real_caller(monkeypatch, format_mode, body_id):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("equipped")
    doc["runtimeProgram"]["entities"][0]["id"] = body_id
    doc["runtimeProgram"]["primaryEntityId"] = body_id
    row["action"] = {}
    expected = deepcopy(doc)
    assert validate_runtime_program(expected)["ok"]
    _assert_delivery(expected)  # The complete, unfiltered candidate is independently valid.
    row["input"] = "invalid_input"
    before = json.dumps(doc, sort_keys=True)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["bindings"] == [{"id": row["id"], "paths": ["input"]}]
    assert scope["identityChanges"]["bindingActionIds"] == []
    assert scope["identityChanges"]["bindingTargetIds"] == []
    assert scope["bindingAlternatives"] == [{"bindingId": row["id"], "allowed": [{"input": "equipped"}]}]
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "input only; empty action is frozen", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [deepcopy(expected["runtimeProgram"]["bindings"][0])],
    }, format_mode)
    assert dossier["repairScope"] == scope
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ok"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert repaired["runtimeProgram"]["bindings"][0]["action"] == {}
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("source_shape", ["omitted", "empty", "explicit"])
@pytest.mark.parametrize("body_id", ["item", "opaque_body"])
def test_input_only_repair_ignores_hostile_frozen_binding_lanes(monkeypatch, format_mode, source_shape, body_id):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("equipped")
    doc["runtimeProgram"]["entities"][0]["id"] = body_id
    doc["runtimeProgram"]["primaryEntityId"] = body_id
    if source_shape == "empty":
        row["action"] = {}
    elif source_shape == "explicit":
        row.update(_explicit(doc, row))
    expected = deepcopy(doc)
    row["input"] = "invalid_input"
    before = json.dumps(doc, sort_keys=True)
    hostile = {"id": row["id"], "input": "equipped",
               "action": {"kind": "equip_passive", "targetId": "foreign_body"},
               "stackCost": 1, "contactDamage": True}
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    filtered, audit = filter_repair_patch_scope(doc, {"note": "frozen hostile lanes", "bindingsUpsert": [hostile]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    assert apply_repair_patch(doc, filtered) == expected
    # The serialized caller also enforces provider grammar before frozen merge;
    # send a grammar-valid foreign target and redundant fixed literals there.
    correction = {"id": row["id"], "input": "equipped",
                  "action": {"kind": "equip_passive", "targetId": "foreign_body"},
                  "stackCost": 0, "contactDamage": False}
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "input only; hostile action/cost/contact ignored", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [correction],
    }, format_mode)
    scope = dossier["repairScope"]
    assert scope["fieldPermissions"]["bindings"] == [{"id": row["id"], "paths": ["input"]}]
    assert scope["identityChanges"]["bindingActionIds"] == []
    assert scope["identityChanges"]["bindingTargetIds"] == []
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    assert audit["ok"] and audit["ignoredChanges"]
    assert audit["acceptedPaths"] == ["$.bindingsUpsert[0].input", "$.realizationReplacement"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)


@pytest.mark.parametrize("attack", ["no-input-authority", "no-input-permission", "missing-alternatives",
                                    "unoffered-input", "unknown-input", "ambiguous-input",
                                    "wrong-target", "wrong-kind", "wrong-stack-cost"])
def test_empty_action_dependency_comparison_requires_exact_scoped_proof(attack):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, validate_repair_patch_scope

    doc, row = _binding_case("equipped")
    row.update(input="invalid_input", action={})
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    candidate = {**deepcopy(row), "input": "equipped"}
    if attack == "no-input-authority":
        scope["identityChanges"]["bindingInputIds"] = []
    elif attack == "no-input-permission":
        scope["fieldPermissions"]["bindings"][0]["paths"] = []
    elif attack == "missing-alternatives":
        scope["bindingAlternatives"] = []
    elif attack == "unoffered-input":
        candidate["input"] = "hold"
    elif attack in {"unknown-input", "ambiguous-input"}:
        candidate["input"] = "unknown" if attack == "unknown-input" else "primary_use"
    elif attack == "wrong-target":
        candidate["action"]["targetId"] = "foreign_body"
    elif attack == "wrong-kind":
        candidate["action"]["kind"] = "hold_entity"
    else:
        candidate["stackCost"] = 1
    before = json.dumps(doc, sort_keys=True)
    report = validate_repair_patch_scope(doc, {"note": "no broad dependency defaults", "bindingsUpsert": [candidate]}, scope)
    assert not report["ok"]
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("body_ids", [[], ["body_a", "body_b"]], ids=["no-body", "ambiguous-body"])
def test_empty_action_input_correction_never_selects_missing_or_ambiguous_body(body_ids):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch

    doc, row = _binding_case("equipped")
    doc["runtimeProgram"]["entities"] = [{"id": body_id, "kind": "item_body"} for body_id in body_ids]
    row.update(input="invalid_input", action={})
    before = json.dumps(doc, sort_keys=True)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    filtered, _ = filter_repair_patch_scope(doc, {
        "note": "input correction cannot create an owner",
        "bindingsUpsert": [{**deepcopy(row), "input": "equipped"}],
    }, scope)
    repaired = apply_repair_patch(doc, filtered)
    assert not validate_runtime_program(repaired)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(repaired)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("case,leaf,value", [
    ("equipped", "kind", "use_item_body"),
    ("equipped", "stackCost", False),
    ("equipped", "contactDamage", 0),
])
def test_fixed_literal_source_aware_receipts_refuse_source_only_typed_forgeries(case, leaf, value):
    doc, row = _binding_case(case)
    row.update(_explicit(doc, row))
    final = _assert_delivery(doc)
    forged = deepcopy(doc)
    target = forged["runtimeProgram"]["bindings"][0]
    (target["action"] if leaf == "kind" else target)[leaf] = value
    assert not audit_compiler_receipts(final["runtimeContract"]["finalWireReceipts"],
                                       authored_document=forged, final_document=final)["ok"]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_placement_fixed_cost_repair_does_not_thaw_valid_action_presence(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("placement")
    row["stackCost"] = 0
    expected = deepcopy(doc)
    expected["runtimeProgram"]["bindings"][1]["stackCost"] = 1
    correction = _explicit(doc, row)
    correction["action"]["placementCallId"] = "other_placement"
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "escrow cost only; target presence and payload frozen", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [correction],
    }, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == [{"id": row["id"], "paths": ["stackCost"]}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("invalid_target", ["unknown", None, False, 2, {}])
@pytest.mark.parametrize("grouped", [False, True])
def test_effect_binding_target_repair_reuses_existing_consumer(monkeypatch, format_mode, invalid_target, grouped):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("effects")
    doc["runtimeProgram"]["entities"][0]["id"] = "opaque_body"
    doc["runtimeProgram"]["primaryEntityId"] = "opaque_body"
    row.update(_explicit(doc, row))
    row.update(stackCost=1, stackConsumeChancePercent=35)
    if grouped:
        row["action"]["effectGroupId"] = "chosen_group"
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "move_player_on_use")["params"]["effectGroupId"] = "chosen_group"
    expected = deepcopy(doc)
    assert validate_runtime_program(expected)["ok"]
    candidate = deepcopy(row)
    row["action"]["targetId"] = deepcopy(invalid_target)
    before = json.dumps(doc, sort_keys=True)
    candidate["stackConsumeChancePercent"] = 99
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "repair only the existing consumer target", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [candidate],
    }, format_mode)
    scope = dossier["repairScope"]
    assert scope["create"]["bindings"]["allowed"] is False
    assert scope["fieldPermissions"]["bindings"] == [{"id": row["id"], "paths": ["action.targetId", "target"]}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)


@pytest.mark.parametrize("candidate_target", ["still_unknown", "omitted", "no_upsert"])
def test_effect_binding_target_dependency_requires_explicit_exact_repair(candidate_target):
    from infini_local.core.runtime_authoring import apply_repair_patch, build_runtime_repair_scope, filter_repair_patch_scope

    doc, row = _binding_case("effects")
    row.update(_explicit(doc, row))
    row["action"]["targetId"] = "unknown"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    candidate = deepcopy(row)
    if candidate_target == "omitted":
        candidate["action"].pop("targetId")
    else:
        candidate["action"]["targetId"] = candidate_target
    filtered, audit = filter_repair_patch_scope(doc, {
        "note": "invalid references and omissions are never repaired by the host",
        "bindingsUpsert": [] if candidate_target == "no_upsert" else [candidate],
    }, scope)
    assert not audit["ok"] or not validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]


@pytest.mark.parametrize("consumer", ["absent", "different_action", "different_group"])
def test_effect_dependency_does_not_retarget_frozen_or_unrelated_consumer(consumer):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope

    doc, row = _binding_case("effects")
    row.update(_explicit(doc, row))
    if consumer == "absent":
        doc["runtimeProgram"]["bindings"] = []
    elif consumer == "different_action":
        row["action"]["kind"] = "use_item_body"
    else:
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "move_player_on_use")["params"]["effectGroupId"] = "unconsumed_group"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["create"]["bindings"]["allowed"] is True
    assert row["id"] not in scope["identityChanges"]["bindingTargetIds"]
    # A different primary action may be explicitly relocated by the existing
    # dependency policy, but its target is never granted a rewrite.


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_effect_target_repair_keeps_both_authored_consumers(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("effects")
    row.update(_explicit(doc, row))
    alternate = {**deepcopy(row), "id": "alternate_effects", "input": "alternate_use"}
    doc["runtimeProgram"]["bindings"].append(alternate)
    expected = deepcopy(doc)
    assert validate_runtime_program(expected)["ok"]
    corrections = deepcopy(doc["runtimeProgram"]["bindings"])
    for binding in doc["runtimeProgram"]["bindings"]:
        binding["action"]["targetId"] = "unknown"
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "repair both invalid references without selecting or adding a consumer",
        "realizationReplacement": doc["realization"], "bindingsUpsert": corrections,
    }, format_mode)
    assert dossier["repairScope"]["create"]["bindings"]["allowed"] is False
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_effect_binding_wrong_target_kind_freezes_action_siblings(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = build_capability_witness("move_straight")
    effects, row = _binding_case("effects")
    call = deepcopy(next(c for c in effects["runtimeProgram"]["calls"] if c["fn"] == "move_player_on_use"))
    call["id"] = "extra_effect"
    doc["runtimeProgram"]["calls"].append(call)
    row.update(id="extra_binding", input="alternate_use")
    row.update(_explicit(effects, row))
    doc["runtimeProgram"]["bindings"].append(row)
    expected = deepcopy(doc)
    assert validate_runtime_program(expected)["ok"]
    candidate = deepcopy(row)
    row["action"]["targetId"] = "witness_entity"
    candidate["action"]["kind"] = "use_item_body"
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "exact target correction cannot rewrite the valid action",
        "realizationReplacement": doc["realization"], "bindingsUpsert": [candidate],
    }, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == [
        {"id": row["id"], "paths": ["action.targetId", "target"]}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("contact", [False, True])
@pytest.mark.parametrize("invalid_leaf", ["contactDamage", "stackCost", "stackConsumeChancePercent"])
def test_compound_effect_consumer_target_and_contact_repair(monkeypatch, format_mode, contact, invalid_leaf):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("effects")
    row.update(_explicit(doc, row))
    row.update(stackCost=1, stackConsumeChancePercent=23, contactDamage=contact)
    row["action"]["effectGroupId"] = "independent_group"
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "move_player_on_use")["params"]["effectGroupId"] = "independent_group"
    expected = deepcopy(doc)
    _assert_delivery(expected)
    candidate = deepcopy(row)
    row["action"]["targetId"] = "foreign_body"
    row[invalid_leaf] = "invalid"
    before = json.dumps(doc, sort_keys=True)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "explicit compound consumer correction", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [candidate],
    }, format_mode)
    scope = dossier["repairScope"]
    assert scope["create"]["bindings"]["allowed"] is False
    assert scope["fieldPermissions"]["bindings"] == [{
        "id": row["id"], "paths": sorted(["action.targetId", invalid_leaf, "target"])}]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)

    # Frozen group, input and every valid sibling survive hostile full rows.
    hostile = deepcopy(candidate)
    hostile["action"]["effectGroupId"] = "foreign_group"
    hostile["input"] = "alternate_use"
    for leaf, value in {"contactDamage": not contact, "stackCost": 0,
                        "stackConsumeChancePercent": 97}.items():
        if leaf != invalid_leaf:
            hostile[leaf] = value
    if format_mode == "json_schema":
        # The strict provider union only admits chance on a cost=1 row.
        hostile["stackCost"] = 1
    again, _ = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "hostile valid siblings stay frozen", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [hostile],
    }, format_mode)
    assert again["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    again.pop("debug")
    assert json.dumps(again, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(again)

    from infini_local.core.errors import PlannerUnavailable
    incomplete = deepcopy(candidate)
    incomplete.pop(invalid_leaf)
    for incoming in ([], [incomplete]):
        with pytest.raises(PlannerUnavailable):
            _offline_gameplay_repair(monkeypatch, doc, {
                "note": "the host must not finish the compound correction",
                "realizationReplacement": doc["realization"], "bindingsUpsert": incoming,
            }, format_mode)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_named_effect_kind_repair_reuses_explicit_body_consumer(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("effects")
    row.update(_explicit(doc, row))
    row["action"]["effectGroupId"] = "chosen_group"
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "move_player_on_use")["params"]["effectGroupId"] = "chosen_group"
    expected = deepcopy(doc)
    candidate = deepcopy(row)
    row["action"].pop("kind")
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "restore the authored named consumer action", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [candidate],
    }, format_mode)
    assert dossier["repairScope"]["create"]["bindings"]["allowed"] is False
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("case", ["body", "effects", "named_effects", "placement"])
@pytest.mark.parametrize("kind_state", ["absent", "null"])
def test_missing_action_kind_repair_preserves_omitted_body_target(monkeypatch, format_mode, case, kind_state):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("effects" if case == "named_effects" else case)
    if case == "named_effects":
        row["action"]["effectGroupId"] = "chosen_group"
        row.update(stackCost=1, stackConsumeChancePercent=35)
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "move_player_on_use")["params"]["effectGroupId"] = "chosen_group"
    doc["runtimeProgram"]["entities"][0]["id"] = "opaque_body"
    if doc["runtimeProgram"]["primaryEntityId"] == "item":
        doc["runtimeProgram"]["primaryEntityId"] = "opaque_body"
    expected = deepcopy(doc)
    candidate = deepcopy(row)
    if kind_state == "absent":
        row["action"].pop("kind")
    else:
        row["action"]["kind"] = None
    before = json.dumps(doc, sort_keys=True)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "the model selects the exact missing action only", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [candidate],
    }, format_mode)
    scope = dossier["repairScope"]
    assert scope["fieldPermissions"]["bindings"] == [{"id": row["id"], "paths": ["action.kind"]}]
    assert scope["identityChanges"]["bindingTargetIds"] == []
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("alternate_error", ["target", "kind"])
def test_consumer_repair_does_not_choose_other_unresolved_actions(monkeypatch, format_mode, alternate_error):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, primary = _binding_case("body")
    effects, alternate = _binding_case("effects")
    effect_call = deepcopy(next(c for c in effects["runtimeProgram"]["calls"] if c["fn"] == "move_player_on_use"))
    effect_call["id"] = "effect"
    doc["runtimeProgram"]["calls"].append(effect_call)
    alternate.update(id="effect_binding", input="alternate_use")
    alternate["action"]["targetId"] = "item"
    doc["runtimeProgram"]["bindings"].append(alternate)
    expected = deepcopy(doc)
    assert validate_runtime_program(expected)["ok"]
    corrections = deepcopy(doc["runtimeProgram"]["bindings"])
    primary["action"].pop("kind")
    if alternate_error == "target":
        alternate["action"]["targetId"] = "unknown"
    else:
        alternate["action"].pop("kind")
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "model selects primary body and alternate effects independently",
        "realizationReplacement": doc["realization"], "bindingsUpsert": corrections,
    }, format_mode)
    assert dossier["repairScope"]["create"]["bindings"]["allowed"] is False
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("leaf", ["stackCost", "contactDamage", "foreign", "action.foreign"])
def test_sparse_input_alternatives_project_only_exact_diagnosed_siblings(leaf):
    from infini_local.core.runtime_authoring import apply_repair_patch, build_runtime_repair_scope, filter_repair_patch_scope

    doc = build_capability_witness("configure_accessory")
    binding = doc["runtimeProgram"]["bindings"][0]
    if leaf == "action.foreign":
        binding["action"] = {}
    expected = deepcopy(doc)
    candidate = deepcopy(binding)
    binding.pop("input")
    if leaf == "action.foreign":
        binding["action"]["foreign"] = 3
    else:
        binding[leaf] = "invalid"
    if leaf in {"stackCost", "contactDamage"}:
        candidate[leaf] = 0 if leaf == "stackCost" else False
        expected["runtimeProgram"]["bindings"][0][leaf] = candidate[leaf]
    before = deepcopy(doc)
    # The scope owner receives exact diagnostics; the shared union diagnostic
    # regression separately proves this complete failure report is generated.
    errors = [
        {"path": "$.runtimeProgram.bindings[0].input", "code": "shape_required"},
        {"path": "$.runtimeProgram.bindings[0]." + leaf,
         "code": "shape_type" if leaf in {"stackCost", "contactDamage"} else "shape_additional_property"},
    ]
    scope = build_runtime_repair_scope(doc, errors)
    assert scope["fieldPermissions"]["bindings"] == [
        {"id": binding["id"], "paths": sorted(["input", leaf])},
    ]
    assert scope["bindingAlternatives"] == [{"bindingId": binding["id"], "allowed": [{"input": "equipped"}]}]
    patch = {"note": "explicit exact corrections", "bindingsUpsert": [candidate]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"], audit
    result = apply_repair_patch(doc, filtered)
    assert result == expected
    assert doc == before
    assert validate_runtime_program(result)["ok"]
    assert validate_runtime_wire(compile_runtime_program(result))["ok"]

    # A candidate input alone cannot make the invalid sibling executable.
    noop = {"note": "only input supplied", "bindingsUpsert": [{**deepcopy(binding), "input": "equipped"}]}
    untouched, no_op_audit = filter_repair_patch_scope(doc, noop, scope)
    assert not no_op_audit["ok"] or not validate_runtime_program(apply_repair_patch(doc, untouched))["ok"]

    # Without a diagnostic for the bad sibling, it remains frozen and blocks
    # every alternative rather than silently receiving a fixed value/removal.
    frozen_scope = build_runtime_repair_scope(doc, errors[:1])
    assert frozen_scope["bindingAlternatives"] == [{"bindingId": binding["id"], "allowed": []}]
    assert doc == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("invalid_target", [None, False, 0, "", [], {}, "unknown"])
@pytest.mark.parametrize("root", ["pure", "hybrid"])
def test_placement_target_repair_distinguishes_invalid_presence(monkeypatch, format_mode, invalid_target, root):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("placement")
    if root == "pure":
        doc = build_capability_witness("configure_tile_placement")
        row = doc["runtimeProgram"]["bindings"][0]
    row.update(_explicit(doc, row))
    expected = deepcopy(doc)
    candidate = deepcopy(row)
    row["action"]["targetId"] = deepcopy(invalid_target)
    before = json.dumps(doc, sort_keys=True)
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "repair the explicit invalid placement target", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [candidate],
    }, format_mode)
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("root", ["pure", "hybrid"])
@pytest.mark.parametrize("explicit_envelope", [False, True])
def test_placement_action_selection_requires_explicit_call_reference(monkeypatch, format_mode, root, explicit_envelope):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("placement")
    if root == "pure":
        doc = build_capability_witness("configure_tile_placement")
        row = doc["runtimeProgram"]["bindings"][0]
    expected = deepcopy(doc)
    candidate = deepcopy(row)
    if explicit_envelope:
        candidate.update(_explicit(doc, candidate))
    row["action"] = {}
    before = json.dumps(doc, sort_keys=True)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "explicitly select placement and its required existing call", "realizationReplacement": doc["realization"],
        "bindingsUpsert": [candidate],
    }, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == [
        {"id": row["id"], "paths": ["action.kind", "action.placementCallId"]}]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("invalid_reference", ["unknown_reference", None, False, 2, {}, [], "witness_call"])
def test_missing_kind_present_invalid_placement_reference_repair(monkeypatch, format_mode, invalid_reference):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("placement")
    expected = deepcopy(doc)
    candidate = deepcopy(row)
    _assert_delivery(expected)
    if invalid_reference == "witness_call":
        invalid_reference = next(c["id"] for c in doc["runtimeProgram"]["calls"]
                                 if c["fn"] == "configure_item_stats")
    row["action"] = {"placementCallId": deepcopy(invalid_reference)}
    before = json.dumps(doc, sort_keys=True)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "explicit kind and exact invalid reference correction",
        "realizationReplacement": doc["realization"], "bindingsUpsert": [candidate],
    }, format_mode)
    scope = dossier["repairScope"]
    assert scope["create"]["bindings"]["allowed"] is False
    assert scope["fieldPermissions"]["bindings"] == [{
        "id": row["id"], "paths": ["action.kind", "action.placementCallId"]}]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)

    hostile = deepcopy(candidate)
    hostile["input"] = "primary_use"
    hostile["action"]["targetId"] = "foreign_body"
    again, _ = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "do not thaw input or accepted target omission",
        "realizationReplacement": doc["realization"], "bindingsUpsert": [hostile],
    }, format_mode)
    assert again["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    again.pop("debug")
    assert json.dumps(again, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(again)

    from infini_local.core.errors import PlannerUnavailable
    incomplete = deepcopy(candidate)
    incomplete["action"].pop("placementCallId")
    foreign = deepcopy(candidate)
    foreign["action"]["placementCallId"] = "unknown_reference"
    for incoming in ([], [incomplete], [foreign]):
        with pytest.raises(PlannerUnavailable):
            _offline_gameplay_repair(monkeypatch, doc, {
                "note": "no host-selected placement reference",
                "realizationReplacement": doc["realization"], "bindingsUpsert": incoming,
            }, format_mode)
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_missing_kind_keeps_valid_placement_reference_frozen(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("placement")
    expected = deepcopy(doc)
    candidate = deepcopy(row)
    row["action"].pop("kind")
    candidate["action"]["placementCallId"] = "unknown_reference"
    before = json.dumps(doc, sort_keys=True)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "valid existing placement reference remains frozen",
        "realizationReplacement": doc["realization"], "bindingsUpsert": [candidate],
    }, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == [{
        "id": row["id"], "paths": ["action.kind"]}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(doc, sort_keys=True) == before
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_placement_target_repair_freezes_valid_reference_and_use_lanes(monkeypatch, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("placement")
    row.update(_explicit(doc, row))
    expected = deepcopy(doc)
    candidate = deepcopy(row)
    row["action"]["targetId"] = None
    candidate["action"]["placementCallId"] = "unrelated_call"
    candidate["input"] = "primary_use"
    candidate["stackCost"] = 0
    candidate["contactDamage"] = True
    # Deliberately wrong fixed values use the real local structural boundary;
    # strict provider-schema emission is covered separately with legal literals.
    if format_mode == "json_schema":
        candidate.update(stackCost=1, contactDamage=False)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "only target is mutable; retain valid reference and use policy",
        "realizationReplacement": doc["realization"], "bindingsUpsert": [candidate],
    }, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == [
        {"id": row["id"], "paths": ["action.targetId", "target"]}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    _assert_delivery(repaired)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("choice", ["missing_reference", "foreign_reference", "omitted_target", "no_upsert"])
def test_placement_selector_repair_never_supplies_missing_model_values(monkeypatch, format_mode, choice):
    from infini_local.core.errors import PlannerUnavailable
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc, row = _binding_case("placement")
    row.update(_explicit(doc, row))
    candidate = deepcopy(row)
    if choice in {"missing_reference", "foreign_reference"}:
        row["action"] = {}
        if choice == "missing_reference":
            candidate["action"].pop("placementCallId")
        else:
            candidate["action"]["placementCallId"] = "unrelated_call"
    else:
        row["action"]["targetId"] = None
        candidate["action"].pop("targetId")
    before = json.dumps(doc, sort_keys=True)
    with pytest.raises(PlannerUnavailable):
        _offline_gameplay_repair(monkeypatch, doc, {
            "note": "no implicit selector or reference completion", "realizationReplacement": doc["realization"],
            "bindingsUpsert": [] if choice == "no_upsert" else [candidate],
        }, format_mode)
    assert json.dumps(doc, sort_keys=True) == before
