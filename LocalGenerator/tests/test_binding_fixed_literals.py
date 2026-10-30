"""Exact redundant binding literals preserve mechanics and source presence."""
from copy import deepcopy
import json

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


from repair_test_helpers import (
    DELETE, binding_case as _binding_case, explicit_binding as _explicit,
    assert_delivery as _assert_delivery, assert_repaired_source,
    binding_transaction as binding_transaction, edit_fields, gameplay_repair as _offline_gameplay_repair,
)


@pytest.mark.parametrize("root", ["body", "spawn"])
@pytest.mark.parametrize("contact_damage", [False, True])
def test_native_tool_stats_are_identical_across_independent_primary_contact(root, contact_damage):
    doc = build_capability_witness("tool_stats") if root == "body" else build_runtime_fixture("workbench_blade")
    if root == "spawn":
        doc["runtimeProgram"]["calls"].append({"id": "native_tool", "fn": "tool_stats", "params": {
            "pickPower": 190, "axePower": 45, "hammerPower": 20, "miningSpeedMultiplier": 0.75}})
    else:
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "tool_stats")["params"] = {
            "pickPower": 190, "axePower": 45, "hammerPower": 20, "miningSpeedMultiplier": 0.75}
    doc["runtimeProgram"]["bindings"][0]["contactDamage"] = contact_damage
    final = _assert_delivery(doc)
    assert {key: final["gameplay"][key] for key in ("pickPower", "axePower", "hammerPower", "miningSpeedScale")} == {
        "pickPower": 190, "axePower": 9, "hammerPower": 20, "miningSpeedScale": 0.75}
    assert final["runtimeProgram"]["bindings"][0]["usePolicy"]["contactDamage"] is contact_damage


@pytest.mark.parametrize("case", ["alternate-only", "equipped-only", "effects-primary", "placement-primary", "missing-item-use"])
def test_native_tool_requires_legitimate_primary_root_not_arbitrary_binding(case):
    doc = build_capability_witness("tool_stats")
    row = doc["runtimeProgram"]["bindings"][0]
    if case == "alternate-only":
        row["input"] = "alternate_use"
    elif case == "equipped-only":
        row.update(input="equipped", action={"kind": "equip_passive"})
        row.pop("stackCost")
        row.pop("contactDamage")
        doc["runtimeProgram"]["calls"].append({"id": "equipped", "fn": "accessory", "params": {"defensePoints": 1}})
    elif case == "effects-primary":
        row["action"] = {"kind": "apply_item_effects"}
        doc["runtimeProgram"]["calls"].append({"id": "utility", "fn": "restore_resources_on_use", "params": {
            "healLife": 1, "healMana": 0, "usesPotionRules": False}})
    elif case == "placement-primary":
        row.update(action={"kind": "place_item", "placementCallId": "placement"}, stackCost=1, contactDamage=False)
        doc["runtimeProgram"]["calls"].append({"id": "placement", "fn": "place_tile", "params": {"tileId": 1, "placeStyle": 0}})
    else:
        doc["runtimeProgram"]["calls"] = [c for c in doc["runtimeProgram"]["calls"] if c["fn"] != "item_use"]
    before = json.dumps(doc, sort_keys=True)
    report = validate_runtime_program(doc)
    tool_index = next(i for i, c in enumerate(doc["runtimeProgram"]["calls"]) if c["fn"] == "tool_stats")
    code = "missing_capability_dependency" if case == "missing-item-use" else "missing_binding_dependency"
    assert [e["code"] for e in report["errors"]] == ([code, "binding_dependency"] if case == "missing-item-use" else [code])
    assert any(e["code"] == code and e["path"] == f"$.runtimeProgram.calls[{tool_index}]" for e in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert json.dumps(doc, sort_keys=True) == before


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


@pytest.mark.parametrize("case,explicit,format_mode", [
    pytest.param("equipped", True, "json_schema", id="explicit-equipped"),
    pytest.param("hold", False, "json_object", id="sparse-hold"),
    pytest.param("body", True, "json_object", id="explicit-body"),
    pytest.param("effects", False, "json_schema", id="sparse-effects"),
    pytest.param("placement", True, "json_object", id="explicit-placement"),
])
def test_binding_input_leaf_repair_preserves_exact_envelope(
    monkeypatch, binding_transaction, format_mode, case, explicit,
):
    transaction = binding_transaction(case, explicit=explicit)
    transaction.row["input"] = "not_an_input"
    if explicit:
        removal = {"action.kind": DELETE} if case in {"equipped", "hold"} else {}
        if case != "hold":
            removal["action.targetId"] = DELETE
        if case in {"equipped", "hold", "placement"}:
            removal.update(stackCost=DELETE, contactDamage=DELETE)
        edit_fields(transaction.candidate, removal)
        if not transaction.candidate["action"]:
            transaction.candidate.pop("action")
    else:
        transaction.candidate = _explicit(transaction.doc, transaction.candidate)
    permissions = ([{"id": "alternate_place", "paths": ["input"]}, {"id": "primary_tool", "paths": ["input"]}]
                   if case == "placement" else None)
    transaction.repair(monkeypatch, format_mode, paths=["input"], permissions=permissions)


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_missing_effects_binding_creation_accepts_explicit_fixed_transaction(monkeypatch, format_mode):

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
    assert_repaired_source(repaired, expected)


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


@pytest.mark.parametrize("case,explicit,format_mode", [
    pytest.param("equipped", True, "json_schema", id="explicit-equipped"),
    pytest.param("hold", False, "json_object", id="sparse-hold"),
    pytest.param("body", True, "json_object", id="explicit-body"),
    pytest.param("effects", False, "json_schema", id="sparse-effects"),
    pytest.param("placement", True, "json_object", id="explicit-placement"),
])
def test_unrelated_repair_freezes_fixed_literal_presence_and_choices(monkeypatch, binding_transaction, format_mode, case, explicit):
    transaction = binding_transaction(case, explicit=explicit)
    sparse, sparse_row = _binding_case(case)
    hostile = sparse_row if explicit else _explicit(sparse, sparse_row)
    if case in {"body", "effects"}:
        hostile.update(stackCost=1, contactDamage=not transaction.row["contactDamage"])
        hostile["action"]["kind"] = "apply_item_effects" if case == "body" else "use_item_body"
    stats = next(c for c in transaction.doc["runtimeProgram"]["calls"] if c["fn"] == "item_stats")
    correction = deepcopy(stats)
    stats["params"]["damage"] = True
    before = json.dumps(transaction.doc, sort_keys=True)
    repaired, dossier = _offline_gameplay_repair(monkeypatch, transaction.doc, {
        "note": "damage correction; binding frozen", "realizationReplacement": transaction.doc["realization"],
        "callsUpsert": [correction], "bindingsUpsert": [hostile]}, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == []
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert_repaired_source(repaired, transaction.expected)
    assert json.dumps(transaction.doc, sort_keys=True) == before


@pytest.mark.parametrize("case,explicit,group,values,broken,hostile,paths", [
    pytest.param("equipped", True, None, {}, {"action.kind": "spawn_entity"}, {},
                 ["action", "action.kind", "action.targetId", "input", "target"], id="fixed-kind"),
    pytest.param("equipped", True, None, {}, {"action.targetId": "foreign_body"}, {},
                 ["action.targetId", "target"], id="fixed-body-target"),
    pytest.param("equipped", True, None, {}, {"stackCost": 1}, {},
                 ["stackCost"], id="fixed-cost"),
    pytest.param("equipped", True, None, {}, {"contactDamage": True}, {},
                 ["contactDamage"], id="fixed-contact"),
    pytest.param("equipped", True, None, {}, {"stackCost": False}, {"action.targetId": "foreign_body"},
                 ["stackCost"], id="boolean-cost-hostile-target"),
    pytest.param("effects", True, "chosen_group", {"stackCost": 1, "stackConsumeChancePercent": 35},
                 {"input": "not_an_input"}, {"action.effectGroupId": "other_group", "stackConsumeChancePercent": 99},
                 ["input"], id="input-only-group-and-chance-frozen"),
    pytest.param("placement", False, None, {}, {"stackCost": 0},
                 {"action.kind": "place_item", "action.targetId": "item", "action.placementCallId": "other_placement",
                  "contactDamage": False}, ["stackCost"], id="placement-cost-action-presence-frozen"),
    pytest.param("placement", False, None, {}, {"action.kind": DELETE},
                 {"action.placementCallId": "unknown_reference"}, ["action.kind"], id="placement-kind-valid-reference-frozen"),
    pytest.param("placement", True, None, {}, {"action.targetId": None},
                 {"action.placementCallId": "unrelated_call", "input": "primary_use", "stackCost": 0,
                  "contactDamage": True}, ["action.targetId", "target"], id="placement-target-valid-use-frozen"),
    pytest.param("effects", True, "chosen_group", {}, {"action.kind": DELETE}, {},
                 ["action.kind"], id="named-effect-kind-existing-consumer"),
])
def test_fixed_leaf_transaction_repair(monkeypatch, binding_transaction, case, explicit, group, values, broken, hostile, paths):
    format_mode = "json_schema"
    transaction = binding_transaction(case, explicit=explicit, group=group, values=values)
    edit_fields(transaction.row, broken)
    edit_fields(transaction.candidate, hostile)
    if case == "placement" and "stackCost" in broken:
        # Original control explicitly repaired cost=1; sparse valid input omitted it.
        transaction.candidate["stackCost"] = 1
        transaction.expected["runtimeProgram"]["bindings"][1]["stackCost"] = 1
    if format_mode == "json_schema" and case == "placement" and "action.targetId" in broken:
        transaction.candidate.update(stackCost=1, contactDamage=False)
    transaction.repair(monkeypatch, format_mode, paths=paths, ignored=bool(hostile),
                       create=False if group and not hostile else None)


@pytest.mark.parametrize("source_shape,body_id", [
    pytest.param("omitted", "item", id="omitted-standard-body"),
    pytest.param("empty", "item", id="empty-standard-body"),
    pytest.param("explicit", "item", id="explicit-standard-body"),
    pytest.param("omitted", "opaque_body", id="omitted-arbitrary-body"),
    pytest.param("empty", "opaque_body", id="empty-arbitrary-body"),
    pytest.param("explicit", "opaque_body", id="explicit-arbitrary-body"),
])
def test_input_only_repair_ignores_hostile_frozen_binding_lanes(monkeypatch, binding_transaction, source_shape, body_id):
    format_mode = "json_schema"
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch

    transaction = binding_transaction("equipped", explicit=source_shape == "explicit", body_id=body_id,
                                      values={"action": {}} if source_shape == "empty" else {})
    transaction.row["input"] = "invalid_input"
    scope = build_runtime_repair_scope(transaction.doc, validate_runtime_program(transaction.doc)["errors"])
    assert scope["bindingAlternatives"] == [{"bindingId": transaction.row["id"], "allowed": [{"input": "equipped"}]}]
    hostile = {"id": transaction.row["id"], "input": "equipped",
               "action": {"kind": "equip_passive", "targetId": "foreign_body"},
               "stackCost": 1, "contactDamage": True}
    filtered, audit = filter_repair_patch_scope(transaction.doc, {"note": "hostile fixed literals", "bindingsUpsert": [hostile]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    assert apply_repair_patch(transaction.doc, filtered) == transaction.expected
    # Provider-valid literals still challenge frozen presence/foreign target.
    transaction.candidate = {**hostile, "stackCost": 0, "contactDamage": False}
    repaired, dossier, _ = transaction.repair(monkeypatch, format_mode, paths=["input"], ignored=True)
    assert dossier["repairScope"] == scope
    assert scope["identityChanges"]["bindingActionIds"] == scope["identityChanges"]["bindingTargetIds"] == []
    assert transaction.audit["ok"]
    assert transaction.audit["acceptedPaths"] == ["$.bindingsUpsert[0].input", "$.realizationReplacement"]


@pytest.mark.parametrize("body_ids", [[], ["body_a", "body_b"]], ids=["no-body", "ambiguous-body"])
def test_empty_action_input_correction_never_selects_missing_or_ambiguous_body(body_ids):
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch

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


@pytest.mark.parametrize("invalid_target,grouped", [
    pytest.param("unknown", False, id="unknown-default"),
    pytest.param(None, False, id="null-default"),
    pytest.param(False, False, id="boolean-default"),
    pytest.param(2, False, id="integer-default"),
    pytest.param({}, False, id="object-default"),
    pytest.param("unknown", True, id="unknown-grouped"),
    pytest.param(None, True, id="null-grouped"),
])
def test_effect_binding_target_repair_reuses_existing_consumer(monkeypatch, binding_transaction, invalid_target, grouped):
    format_mode = "json_schema"
    transaction = binding_transaction("effects", explicit=True, body_id="opaque_body",
                                      group="chosen_group" if grouped else None,
                                      values={"stackCost": 1, "stackConsumeChancePercent": 35})
    transaction.row["action"]["targetId"] = deepcopy(invalid_target)
    transaction.candidate["stackConsumeChancePercent"] = 99
    transaction.repair(monkeypatch, format_mode, paths=["action.targetId", "target"], ignored=True, create=False)


@pytest.mark.parametrize("target,no_upsert", [
    pytest.param("still_unknown", False, id="wrong-reference"),
    pytest.param(DELETE, False, id="omitted-reference"),
    pytest.param("unknown", True, id="no-upsert"),
])
def test_effect_binding_target_dependency_requires_explicit_exact_repair(target, no_upsert):
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope

    doc, row = _binding_case("effects")
    row.update(_explicit(doc, row))
    row["action"]["targetId"] = "unknown"
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    candidate = deepcopy(row)
    edit_fields(candidate, {"action.targetId": target})
    filtered, audit = filter_repair_patch_scope(doc, {"note": "no host-chosen references",
        "bindingsUpsert": [] if no_upsert else [candidate]}, scope)
    assert not audit["ok"] or not validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]
    assert doc == before


@pytest.mark.parametrize("consumer", ["absent", "different_action", "different_group"])
def test_effect_dependency_does_not_retarget_frozen_or_unrelated_consumer(consumer):
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope

    doc, row = _binding_case("effects")
    row.update(_explicit(doc, row))
    if consumer == "absent":
        doc["runtimeProgram"]["bindings"] = []
    elif consumer == "different_action":
        row["action"]["kind"] = "use_item_body"
    else:
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "blink_on_use")["params"]["effectGroupId"] = "unconsumed_group"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["create"]["bindings"]["allowed"] is True
    assert row["id"] not in scope["identityChanges"]["bindingTargetIds"]
    # A different primary action may be explicitly relocated by the existing
    # dependency policy, but its target is never granted a rewrite.


def test_effect_target_repair_keeps_both_authored_consumers(monkeypatch):
    format_mode = "json_schema"
    doc, row = _binding_case("effects")
    row.update(_explicit(doc, row))
    doc["runtimeProgram"]["bindings"].append({**deepcopy(row), "id": "alternate_effects", "input": "alternate_use"})
    expected = deepcopy(doc)
    _assert_delivery(expected)
    corrections = deepcopy(doc["runtimeProgram"]["bindings"])
    for binding in doc["runtimeProgram"]["bindings"]:
        binding["action"]["targetId"] = "unknown"
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, {
        "note": "keep both explicitly authored consumers", "realizationReplacement": doc["realization"],
        "bindingsUpsert": corrections}, format_mode)
    assert dossier["repairScope"]["create"]["bindings"]["allowed"] is False
    assert_repaired_source(repaired, expected)


def test_effect_binding_wrong_target_kind_freezes_action_siblings(monkeypatch, binding_transaction):
    format_mode = "json_schema"
    transaction = binding_transaction("effects", explicit=True)
    effect_call = deepcopy(next(c for c in transaction.doc["runtimeProgram"]["calls"] if c["fn"] == "blink_on_use"))
    doc = build_capability_witness("move_straight")
    effect_call["id"] = "extra_effect"
    doc["runtimeProgram"]["calls"].append(effect_call)
    transaction.row.update(id="extra_binding", input="alternate_use")
    doc["runtimeProgram"]["bindings"].append(transaction.row)
    transaction.doc, transaction.expected = doc, deepcopy(doc)
    transaction.candidate = deepcopy(transaction.row)
    transaction.row["action"]["targetId"] = "witness_entity"
    transaction.candidate["action"]["kind"] = "use_item_body"
    transaction.repair(monkeypatch, format_mode, paths=["action.targetId", "target"], ignored=True)


@pytest.mark.parametrize("format_mode,contact,invalid_leaf", [
    pytest.param("json_object", False, "contactDamage", id="contact-false"),
    pytest.param("json_schema", True, "stackCost", id="cost-true"),
    pytest.param("json_object", False, "stackConsumeChancePercent", id="probability-false"),
])
def test_compound_effect_consumer_target_and_contact_repair(
    monkeypatch, binding_transaction, format_mode, contact, invalid_leaf,
):
    transaction = binding_transaction("effects", explicit=True, group="independent_group",
                                      values={"stackCost": 1, "stackConsumeChancePercent": 23, "contactDamage": contact})
    edit_fields(transaction.row, {"action.targetId": "foreign_body", invalid_leaf: "invalid"})
    hostile = {"action.effectGroupId": "foreign_group", "input": "alternate_use",
               "contactDamage": not contact, "stackCost": 0, "stackConsumeChancePercent": 97}
    hostile.pop(invalid_leaf)
    edit_fields(transaction.candidate, hostile)
    if format_mode == "json_schema":
        transaction.candidate["stackCost"] = 1
    transaction.repair(monkeypatch, format_mode, paths=sorted(["action.targetId", invalid_leaf, "target"]),
                       ignored=True, create=False)


@pytest.mark.parametrize("case,kind_state,format_mode", [
    pytest.param("body", "absent", "json_object", id="body-absent"),
    pytest.param("effects", "null", "json_schema", id="effects-null"),
    pytest.param("named_effects", "absent", "json_object", id="named-effects-absent"),
    pytest.param("placement", "null", "json_schema", id="placement-null"),
])
def test_missing_action_kind_repair_preserves_omitted_body_target(
    monkeypatch, binding_transaction, format_mode, case, kind_state,
):
    transaction = binding_transaction("effects" if case == "named_effects" else case,
                                      body_id="opaque_body", group="chosen_group" if case == "named_effects" else None,
                                      values={"stackCost": 1, "stackConsumeChancePercent": 35} if case == "named_effects" else {})
    edit_fields(transaction.row, {"action.kind": DELETE if kind_state == "absent" else None})
    _, dossier, _ = transaction.repair(monkeypatch, format_mode, paths=["action.kind"])
    assert dossier["repairScope"]["identityChanges"]["bindingTargetIds"] == []


@pytest.mark.parametrize("alternate_error", ["target", "kind"])
def test_consumer_repair_does_not_choose_other_unresolved_actions(monkeypatch, alternate_error):
    format_mode = "json_schema"

    doc, primary = _binding_case("body")
    effects, alternate = _binding_case("effects")
    effect_call = deepcopy(next(c for c in effects["runtimeProgram"]["calls"] if c["fn"] == "blink_on_use"))
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
    assert_repaired_source(repaired, expected)


@pytest.mark.parametrize("leaf", ["stackCost", "contactDamage", "foreign", "action.foreign"])
def test_sparse_input_alternatives_project_only_exact_diagnosed_siblings(leaf):
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope

    doc = build_capability_witness("accessory")
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


@pytest.mark.parametrize("invalid_target,root", [
    pytest.param(None, "pure", id="null-pure"),
    pytest.param(False, "pure", id="boolean-pure"),
    pytest.param(0, "pure", id="integer-pure"),
    pytest.param("", "pure", id="empty-string-pure"),
    pytest.param([], "pure", id="array-pure"),
    pytest.param({}, "pure", id="object-pure"),
    pytest.param("unknown", "pure", id="unknown-pure"),
    pytest.param(None, "hybrid", id="null-hybrid"),
    pytest.param("unknown", "hybrid", id="unknown-hybrid"),
])
def test_placement_target_repair_distinguishes_invalid_presence(monkeypatch, binding_transaction, invalid_target, root):
    format_mode = "json_schema"
    transaction = binding_transaction("pure-placement" if root == "pure" else "placement", explicit=True)
    transaction.row["action"]["targetId"] = deepcopy(invalid_target)
    transaction.repair(monkeypatch, format_mode, paths=["action.targetId", "target"])


@pytest.mark.parametrize("root", ["pure", "hybrid"])
@pytest.mark.parametrize("explicit_envelope", [False, True])
def test_placement_action_selection_requires_explicit_call_reference(monkeypatch, binding_transaction, root, explicit_envelope):
    format_mode = "json_schema"
    transaction = binding_transaction("pure-placement" if root == "pure" else "placement")
    if explicit_envelope:
        transaction.candidate.update(_explicit(transaction.doc, transaction.candidate))
    transaction.row["action"] = {}
    transaction.repair(monkeypatch, format_mode, paths=["action.kind", "action.placementCallId"])


@pytest.mark.parametrize("invalid_reference", [
    pytest.param("unknown_reference", id="unknown"), pytest.param(None, id="null"),
    pytest.param(False, id="boolean"), pytest.param(2, id="integer"),
    pytest.param({}, id="object"), pytest.param([], id="array"),
    pytest.param("witness_call", id="wrong-capability"),
])
def test_missing_kind_present_invalid_placement_reference_repair(monkeypatch, binding_transaction, invalid_reference):
    format_mode = "json_schema"
    transaction = binding_transaction("placement")
    if invalid_reference == "witness_call":
        invalid_reference = next(c["id"] for c in transaction.doc["runtimeProgram"]["calls"] if c["fn"] == "item_stats")
    transaction.row["action"] = {"placementCallId": deepcopy(invalid_reference)}
    transaction.candidate["input"] = "primary_use"
    transaction.candidate["action"]["targetId"] = "foreign_body"
    transaction.repair(monkeypatch, format_mode, paths=["action.kind", "action.placementCallId"], ignored=True, create=False)


@pytest.mark.parametrize("case,broken,omitted,wrong,no_upsert,explicit", [
    pytest.param("placement", {"action": {}}, "action.placementCallId", {}, False, True, id="placement-no-reference"),
    pytest.param("placement", {"action": {}}, None, {"action.placementCallId": "unrelated_call"}, False, True, id="placement-foreign-reference"),
    pytest.param("placement", {"action.targetId": None}, "action.targetId", {}, False, True, id="placement-omitted-target"),
    pytest.param("placement", {"action.targetId": None}, None, {}, True, True, id="placement-no-upsert"),
    pytest.param("placement", {"action": {"placementCallId": "unknown_reference"}}, None, {}, True, False, id="missing-kind-reference-no-upsert"),
    pytest.param("placement", {"action": {"placementCallId": "unknown_reference"}}, "action.placementCallId", {}, False, False, id="missing-kind-reference-incomplete"),
    pytest.param("placement", {"action": {"placementCallId": "unknown_reference"}}, None,
                 {"action.placementCallId": "unknown_reference"}, False, False, id="missing-kind-reference-foreign"),
    pytest.param("effects", {"action.targetId": "foreign_body", "contactDamage": "invalid"}, "contactDamage", {}, False, True, id="compound-missing-contact"),
    pytest.param("effects", {"action.targetId": "foreign_body", "stackCost": "invalid"}, "stackCost", {}, False, True, id="compound-missing-cost"),
    pytest.param("effects", {"action.targetId": "foreign_body", "stackConsumeChancePercent": "invalid"}, "stackConsumeChancePercent", {}, False, True, id="compound-missing-chance"),
    pytest.param("effects", {"action.targetId": "foreign_body", "contactDamage": "invalid"}, None, {}, True, True, id="compound-no-upsert"),
])
def test_incomplete_transaction_never_supplies_missing_model_values(monkeypatch, binding_transaction, case, broken, omitted, wrong, no_upsert, explicit):
    format_mode = "json_schema"
    from infini_local.core.errors import PlannerUnavailable

    transaction = binding_transaction(case, explicit=explicit,
                                      group="independent_group" if case == "effects" else None,
                                      values={"stackCost": 1, "stackConsumeChancePercent": 23, "contactDamage": True} if case == "effects" else {})
    edit_fields(transaction.row, broken)
    edit_fields(transaction.candidate, {**wrong, **({omitted: DELETE} if omitted else {})})
    before = json.dumps(transaction.doc, sort_keys=True)
    with pytest.raises(PlannerUnavailable):
        _offline_gameplay_repair(monkeypatch, transaction.doc, {
            "note": "no implicit completion", "realizationReplacement": transaction.doc["realization"],
            "bindingsUpsert": [] if no_upsert else [transaction.candidate],
        }, format_mode)
    assert json.dumps(transaction.doc, sort_keys=True) == before
    assert not validate_runtime_program(transaction.doc)["ok"]
