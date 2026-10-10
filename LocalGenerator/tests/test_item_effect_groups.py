"""Explicit effect identities select native item effects without carrier entities."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts, EFFECT_GROUP_BINDING_LOWERER_ID
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
from infini_local.qa import primitive_loss_audit


def _groups(fn="restore_resources_on_use"):
    doc = build_capability_witness(fn)
    program = doc["runtimeProgram"]
    call = next(c for c in program["calls"] if c["fn"] == fn)
    call["params"]["effectGroupId"] = "first"
    binding = program["bindings"][0]
    binding["usePolicy"]["action"]["effectGroupId"] = "first"
    alternate = deepcopy(binding)
    alternate.update(id="alternate_effect", input="alternate_use")
    alternate["usePolicy"]["action"]["effectGroupId"] = "second"
    other = deepcopy(call)
    other["id"] = "second_effect"
    other["params"]["effectGroupId"] = "second"
    if fn == "restore_resources_on_use":
        other["params"].update(healLife=0, healMana=35)
    elif fn == "move_player_on_use":
        other["params"].update(mode="blink_to_cursor", rangeTiles=12, cooldownTicks=90)
    elif fn == "recall_home_on_use":
        other["params"]["cooldownTicks"] = 90
    elif fn == "apply_vanilla_buff_on_use":
        other["params"]["buffId"] = 2
    else:
        other["params"].update(lightStrength=0.5, durationTicks=120)
    program["bindings"].append(alternate)
    program["calls"].append(other)
    return doc


@pytest.mark.parametrize("fn", ["restore_resources_on_use", "apply_vanilla_buff_on_use", "apply_generated_buff_on_use", "move_player_on_use", "recall_home_on_use"])
def test_every_existing_item_effect_can_partition_explicit_main_and_alternate_groups(fn):
    doc = _groups(fn)
    before = deepcopy(doc)
    assert validate_runtime_program(doc)["ok"]
    final = compile_runtime_program(doc)
    assert validate_runtime_wire(final)["ok"]
    assert doc == before
    groups = final["runtimeProgram"]["effectGroups"]
    assert [group["id"] for group in groups] == ["first", "second"]
    assert len(final["runtimeProgram"]["entities"]) == 1
    assert {b["input"]: b["usePolicy"]["action"]["effectGroupId"] for b in final["runtimeProgram"]["bindings"]} == {"primary_use": "first", "alternate_use": "second"}
    if fn == "restore_resources_on_use":
        assert [(g["healLife"], g["healMana"]) for g in groups] == [(20, 0), (0, 35)]
    receipts = final["runtimeContract"]["finalWireReceipts"]
    assert sum(row.get("lowererId") == EFFECT_GROUP_BINDING_LOWERER_ID for row in receipts) == 2
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=final)["ok"]


def _mobility_pair(first, second):
    doc = _groups(first)
    replacement = deepcopy(next(row for row in build_capability_witness(second)["runtimeProgram"]["calls"] if row["fn"] == second))
    replacement.update(id="second_effect")
    replacement["params"].update(effectGroupId="second", cooldownTicks=90)
    doc["runtimeProgram"]["calls"][-1] = replacement
    return doc


@pytest.mark.parametrize("first,second", [
    ("move_player_on_use", "move_player_on_use"),
    ("recall_home_on_use", "recall_home_on_use"),
    ("move_player_on_use", "recall_home_on_use"),
    ("recall_home_on_use", "move_player_on_use"),
])
@pytest.mark.parametrize("owner", ["same", "default", "distinct", "named-default"])
def test_mobility_exclusivity_uses_exact_effect_owner_not_input_or_operation(first, second, owner):
    doc = _mobility_pair(first, second)
    effects = [row for row in doc["runtimeProgram"]["calls"] if row["fn"] in {first, second}]
    if owner == "same":
        effects[1]["params"]["effectGroupId"] = "first"
        doc["runtimeProgram"]["bindings"][1]["usePolicy"]["action"]["effectGroupId"] = "first"
    elif owner in {"default", "named-default"}:
        for index in ([0, 1] if owner == "default" else [1]):
            effects[index]["params"].pop("effectGroupId")
            doc["runtimeProgram"]["bindings"][index]["usePolicy"]["action"].pop("effectGroupId")
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    if owner in {"same", "default"}:
        conflicts = [row for row in report["errors"] if row["code"] == "exclusive_component_conflict"]
        assert len(conflicts) == 1
        assert conflicts[0]["relatedIds"] == [effects[0]["id"], effects[1]["id"], "item"]
    else:
        assert report["ok"], report
        final = compile_runtime_program(doc)
        assert validate_runtime_wire(final)["ok"]
        for call in effects:
            group_id = call["params"].get("effectGroupId")
            destination = next(row for row in final["runtimeProgram"]["effectGroups"] if row["id"] == group_id) if group_id else final["gameplay"]
            assert destination["mobilityCooldownTicks"] == call["params"]["cooldownTicks"]
            if call["fn"] == "recall_home_on_use":
                assert {key: destination[key] for key in CAPABILITY_REGISTRY[call["fn"]].fixed_wire_literals} == dict(CAPABILITY_REGISTRY[call["fn"]].fixed_wire_literals)
        receipts = final["runtimeContract"]["finalWireReceipts"]
        assert audit_compiler_receipts(receipts, authored_document=doc, final_document=final)["ok"]
        assert audit_compiler_receipts(receipts, final_document=final)["ok"]
    assert doc == before


@pytest.mark.parametrize("field", ["mobilityMode", "mobilityRangeTiles", "mobilitySafeTileOnly"])
@pytest.mark.parametrize("mutation", ["drop", "duplicate", "wrong_type", "wrong_value", "cross_owner"])
@pytest.mark.parametrize("source_available", [False, True])
def test_named_recall_fixed_literals_have_unique_exact_selected_owner_receipts(field, mutation, source_available):
    doc = _mobility_pair("move_player_on_use", "recall_home_on_use")
    final = compile_runtime_program(doc)
    rows = final["runtimeContract"]["finalWireReceipts"]
    row = next(row for row in rows if row.get("fn") == "recall_home_on_use" and row["finalPath"].endswith("." + field))
    assert row["finalPath"] == "runtimeProgram.effectGroups[1]." + field
    expected = CAPABILITY_REGISTRY["recall_home_on_use"].fixed_wire_literals[field]
    assert row["authoredPath"].endswith(".fn") and type(row["value"]) is type(expected) and row["value"] == expected
    if mutation == "drop":
        rows.remove(row)
    elif mutation == "duplicate":
        rows.append(deepcopy(row))
    elif mutation in {"wrong_type", "wrong_value"}:
        row["value"] = {"mobilityMode": True, "mobilityRangeTiles": False, "mobilitySafeTileOnly": 0}[field] if mutation == "wrong_type" else {
            "mobilityMode": "blink_to_cursor", "mobilityRangeTiles": 1, "mobilitySafeTileOnly": True}[field]
        final["runtimeProgram"]["effectGroups"][1][field] = row["value"]
    else:
        row["finalPath"] = "runtimeProgram.effectGroups[0]." + field
        final["runtimeProgram"]["effectGroups"][0][field] = expected
    assert not audit_compiler_receipts(rows, authored_document=doc if source_available else None, final_document=final)["ok"]
    assert not validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("fn", ["move_player_on_use", "recall_home_on_use"])
@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_mobility_leaf_repair_keeps_group_identity_and_other_effect_frozen(monkeypatch, fn, format_mode):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = _mobility_pair("move_player_on_use", fn)
    call = doc["runtimeProgram"]["calls"][-1]
    call["params"]["cooldownTicks"] = True
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": "second_effect", "paths": ["params.cooldownTicks"]}]
    fixed = deepcopy(call)
    fixed["params"]["cooldownTicks"] = 90
    expected = apply_repair_patch(doc, {"note": "one explicit leaf", "callsUpsert": [fixed]})
    fixed["params"]["effectGroupId"] = "first"
    hostile = deepcopy(doc["runtimeProgram"]["calls"][-2])
    hostile["params"]["rangeTiles"] = 120
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc,
        {"note": "one explicit leaf with frozen attacks", "realizationReplacement": doc["realization"], "callsUpsert": [fixed, hostile]},
        format_mode, out_of_scope_response=fn == "recall_home_on_use")
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert repaired == expected
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


def test_named_and_default_effects_remain_independent():
    doc = _groups()
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "second_effect")
    del call["params"]["effectGroupId"]
    del doc["runtimeProgram"]["bindings"][1]["usePolicy"]["action"]["effectGroupId"]
    final = compile_runtime_program(doc)
    assert len(final["runtimeProgram"]["effectGroups"]) == 1
    assert final["gameplay"]["healLife"] == 0 and final["gameplay"]["healMana"] == 35
    assert final["runtimeProgram"]["effectGroups"][0]["healLife"] == 20


def test_same_named_group_composes_explicit_components():
    doc = _groups()
    buff = next(c for c in build_capability_witness("apply_generated_buff_on_use")["runtimeProgram"]["calls"] if c["fn"] == "apply_generated_buff_on_use")
    buff["id"] = "primary_light"
    buff["params"]["effectGroupId"] = "first"
    doc["runtimeProgram"]["calls"].append(buff)
    final = compile_runtime_program(doc)
    assert "generatedBuff" in final["runtimeProgram"]["effectGroups"][0]
    assert "generatedBuff" not in final["runtimeProgram"]["effectGroups"][1]
    receipts = final["runtimeContract"]["finalWireReceipts"]
    group_claims = [row for row in receipts if row["finalPath"] == "runtimeProgram.effectGroups[0].id"]
    assert len(group_claims) == 2
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=final)["ok"]
    assert audit_compiler_receipts(receipts, final_document=final)["ok"]
    for mode in ("missing", "duplicate", "forged"):
        attacked = deepcopy(receipts)
        claim = next(row for row in attacked if row["finalPath"] == "runtimeProgram.effectGroups[0].id")
        if mode == "missing":
            attacked.remove(claim)
        elif mode == "duplicate":
            attacked.append(deepcopy(claim))
        else:
            claim["value"] = "second"
        assert not audit_compiler_receipts(attacked, authored_document=doc, final_document=final)["ok"], mode
        assert not audit_compiler_receipts(attacked, final_document=final)["ok"], mode


def test_held_refresh_is_explicit_generated_utility_with_no_active_effect_binding():
    doc = build_capability_witness("refresh_generated_effect_group_while_held")
    final = compile_runtime_program(doc)
    assert final["runtimeProgram"]["heldEffectGroupId"] == "witness"
    assert set(final["runtimeProgram"]["effectGroups"][0]) == {"id", "generatedBuff"}
    assert all(b["usePolicy"]["action"]["kind"] != "apply_item_effects" for b in final["runtimeProgram"]["bindings"])
    assert len(final["runtimeProgram"]["entities"]) == 1


@pytest.mark.parametrize("extra", ["restore_resources_on_use", "apply_vanilla_buff_on_use", "move_player_on_use"])
def test_held_refresh_cannot_repeat_instant_heal_native_buffs_or_mobility(extra):
    doc = build_capability_witness("refresh_generated_effect_group_while_held")
    call = next(c for c in build_capability_witness(extra)["runtimeProgram"]["calls"] if c["fn"] == extra)
    call["id"] = "illegal_held_effect"
    call["params"]["effectGroupId"] = "witness"
    doc["runtimeProgram"]["calls"].append(call)
    assert any(e["code"] == "invalid_held_effect_group" for e in validate_runtime_program(doc)["errors"])


@pytest.mark.parametrize("value", [None, True, 3, [], {}, "", "Wrong", "a" * 49])
def test_effect_identity_is_strict_and_not_a_semantic_family(value):
    doc = _groups()
    doc["runtimeProgram"]["bindings"][0]["usePolicy"]["action"]["effectGroupId"] = value
    assert not validate_runtime_program(doc)["ok"]
    final = compile_runtime_program(_groups())
    final.pop("runtimeContract")
    final["runtimeProgram"]["bindings"][0]["usePolicy"]["action"]["effectGroupId"] = value
    assert not validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("held", [False, True])
def test_repair_retargets_only_invalid_reference_and_keeps_effects_frozen(held):
    doc = build_capability_witness("refresh_generated_effect_group_while_held") if held else _groups()
    rows = doc["runtimeProgram"]["calls" if held else "bindings"]
    row = next(r for r in rows if r.get("fn") == "refresh_generated_effect_group_while_held") if held else rows[0]
    holder = row["params"] if held else row["usePolicy"]["action"]
    expected = holder["effectGroupId"]
    holder["effectGroupId"] = "missing"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    corrected = deepcopy(row)
    (corrected["params"] if held else corrected["usePolicy"]["action"])["effectGroupId"] = expected
    if not held:
        corrected["usePolicy"]["stackCost"] = 1
    key = "callsUpsert" if held else "bindingsUpsert"
    filtered, audit = filter_repair_patch_scope(doc, {"note": "Repair exact reference only", key: [corrected]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert validate_runtime_program(repaired)["ok"]
    if not held:
        assert repaired["runtimeProgram"]["bindings"][0]["usePolicy"]["stackCost"] == 0
    if not held:
        assert repaired["runtimeProgram"]["calls"] == doc["runtimeProgram"]["calls"]


def test_unbound_group_repair_names_only_the_existing_group_in_new_consumer():
    doc = _groups()
    doc["runtimeProgram"]["bindings"].pop()
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    allowed = scope["create"]["bindings"]["allowedTransactions"]
    assert allowed and all(row["usePolicy"]["action"].get("effectGroupId") == "second" for row in allowed)
    candidate = {"id": "repaired_alternate", **deepcopy(allowed[0])}
    filtered, audit = filter_repair_patch_scope(doc, {"note": "Attach authored existing group", "bindingsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]


@pytest.mark.parametrize("mutation", ["binding_receipt_drop", "cross_group_receipt", "invent_group", "bad_effect_field", "held_heal", "empty_groups"])
def test_wire_or_receipts_reject_group_aliasing_and_unowned_fields(mutation):
    doc = _groups()
    final = compile_runtime_program(doc)
    receipts = final["runtimeContract"]["finalWireReceipts"]
    if mutation == "binding_receipt_drop":
        receipts[:] = [r for r in receipts if r.get("lowererId") != EFFECT_GROUP_BINDING_LOWERER_ID]
    elif mutation == "cross_group_receipt":
        receipt = next(r for r in receipts if r.get("fn") == "restore_resources_on_use" and r.get("finalPath") == "runtimeProgram.effectGroups[0].healLife")
        receipt["finalPath"] = "runtimeProgram.effectGroups[1].healLife"
        final["runtimeProgram"]["effectGroups"][1]["healLife"] = receipt["value"]
    elif mutation == "invent_group":
        final["runtimeProgram"]["effectGroups"][0]["id"] = "invented"
    elif mutation == "bad_effect_field":
        final["runtimeProgram"]["effectGroups"][0]["damage"] = 999
    elif mutation == "held_heal":
        final["runtimeProgram"]["heldEffectGroupId"] = "first"
    else:
        final["runtimeProgram"]["effectGroups"] = []
    assert not validate_runtime_wire(final)["ok"]


def test_ungrouped_omission_never_materializes_named_groups_or_binding_receipts():
    final = compile_runtime_program(build_capability_witness("restore_resources_on_use"))
    assert "effectGroups" not in final["runtimeProgram"] and "heldEffectGroupId" not in final["runtimeProgram"]
    assert not any(r.get("lowererId") == EFFECT_GROUP_BINDING_LOWERER_ID for r in final["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("held", [False, True])
def test_named_generated_buff_neutral_omissions_have_exact_unique_group_receipts(held):
    doc = build_capability_witness("refresh_generated_effect_group_while_held") if held else _groups("apply_generated_buff_on_use")
    defaults = {name: spec.default for name, spec in CAPABILITY_REGISTRY["apply_generated_buff_on_use"].params.items()
                if spec.default is not None}
    for call in doc["runtimeProgram"]["calls"]:
        if call["fn"] == "apply_generated_buff_on_use":
            for name in defaults:
                call["params"].pop(name, None)
    before = deepcopy(doc)
    final = compile_runtime_program(doc)
    assert doc == before
    rows = final["runtimeContract"]["finalWireReceipts"]
    omissions = [row for row in rows if row.get("status") == "declared_neutral_omission" and row.get("fn") == "apply_generated_buff_on_use"]
    assert len(omissions) == len(defaults) * (1 if held else 2)
    assert all(row["finalPath"].startswith("runtimeProgram.effectGroups[") for row in omissions)
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=final)["ok"]
    assert audit_compiler_receipts(rows, final_document=final)["ok"]
    damaged = deepcopy(final)
    damaged["runtimeContract"]["finalWireReceipts"].remove(omissions[0])
    assert not validate_runtime_wire(damaged)["ok"]


def test_effect_group_surface_audit_rejects_uncatalogued_native_storage():
    source = (primitive_loss_audit._MODEL_ROOT / "Common/Models/RuntimeItemEffectGroupSpec.cs").read_bytes()
    assert primitive_loss_audit.item_effect_group_surface_audit(source)["ok"]
    anchor = b'public string Id { get; set; } = "";'
    assert anchor in source
    changed = source.replace(anchor, b"public int Damage { get; set; }\n    " + anchor)
    report = primitive_loss_audit.item_effect_group_surface_audit(changed)
    assert not report["ok"]
    assert report["unclassifiedDtoFields"] == ["Damage"]


def test_named_group_dto_neutral_serialization_is_accepted_without_new_effects():
    final = compile_runtime_program(build_capability_witness("refresh_generated_effect_group_while_held"))
    final.pop("runtimeContract")  # DTO transport is validated without claiming source receipts.
    group = final["runtimeProgram"]["effectGroups"][0]
    group.update(healLife=0, healMana=0, potion=False, extraBuffs=[], mobilityMode="", mobilityRangeTiles=0,
                 mobilityCooldownTicks=0, mobilitySafeTileOnly=True)
    assert validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_broken_selector_does_not_suppress_independent_group_consumer(monkeypatch, format_mode):
    import json
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = _groups()
    alternate = doc["runtimeProgram"]["bindings"].pop()
    primary = doc["runtimeProgram"]["bindings"][0]
    primary["usePolicy"]["action"]["effectGroupId"] = "missing"
    before = json.dumps(doc, sort_keys=True)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert any(row["input"] == "alternate_use" and row["usePolicy"]["action"]["effectGroupId"] == "second"
               for row in scope["create"]["bindings"]["allowedTransactions"])
    corrected = deepcopy(primary)
    corrected["usePolicy"]["action"]["effectGroupId"] = "first"
    expected = apply_repair_patch(doc, {"note": "model chooses both exact consumers", "bindingsUpsert": [corrected, alternate]})
    corrected["usePolicy"]["stackCost"] = 1
    hostile = deepcopy(doc["runtimeProgram"]["calls"][0])
    hostile["params"]["damage"] = 999
    incoming = {"note": "explicit selector and independent alternate", "realizationReplacement": doc["realization"],
                "bindingsUpsert": [corrected, alternate], "callsUpsert": [hostile]}
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, incoming, format_mode, out_of_scope_response=True)
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_empty_held_domain_allows_only_explicit_invalid_call_deletion(monkeypatch, format_mode):
    import json
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = build_capability_witness("refresh_generated_effect_group_while_held")
    doc["runtimeProgram"]["calls"] = [row for row in doc["runtimeProgram"]["calls"] if row["fn"] != "apply_generated_buff_on_use"]
    held = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "refresh_generated_effect_group_while_held")
    frozen = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    before = json.dumps(doc, sort_keys=True)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["deletable"]["callIds"] == [held["id"]]
    expected = apply_repair_patch(doc, {"note": "explicit optional removal", "callIdsDelete": [held["id"]]})
    hostile = deepcopy(frozen)
    hostile["params"]["damage"] = 999
    incoming = {"note": "remove diagnosed held call only", "realizationReplacement": doc["realization"],
                "callIdsDelete": [held["id"], frozen["id"]], "callsUpsert": [hostile]}
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, incoming, format_mode, out_of_scope_response=True)
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert json.dumps(doc, sort_keys=True) == before

@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_broken_held_selector_cannot_suppress_another_generated_group_consumer(monkeypatch, format_mode):
    import json
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = _groups("apply_generated_buff_on_use")
    bindings = doc["runtimeProgram"]["bindings"]
    alternate = bindings.pop()
    bindings[0]["usePolicy"]["action"] = {"kind": "use_item_body", "targetId": "item"}
    held = deepcopy(next(row for row in build_capability_witness("refresh_generated_effect_group_while_held")["runtimeProgram"]["calls"]
                         if row["fn"] == "refresh_generated_effect_group_while_held"))
    held.update(id="held_selector")
    held["params"]["effectGroupId"] = "missing"
    doc["runtimeProgram"]["calls"].append(held)
    fixed = deepcopy(held)
    fixed["params"]["effectGroupId"] = "first"
    expected = apply_repair_patch(doc, {"note": "two model-chosen consumers", "callsUpsert": [fixed], "bindingsUpsert": [alternate]})
    assert validate_runtime_program(expected)["ok"]
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert any(row["usePolicy"]["action"].get("effectGroupId") == "second"
               for row in scope["create"]["bindings"]["allowedTransactions"])
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc,
        {"note": "held first and explicit alternate second", "realizationReplacement": doc["realization"],
         "callsUpsert": [fixed], "bindingsUpsert": [alternate]}, format_mode)
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_nonempty_held_domain_retargets_but_cannot_delete_valid_utility(monkeypatch, format_mode):
    import json
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = build_capability_witness("refresh_generated_effect_group_while_held")
    held = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "refresh_generated_effect_group_while_held")
    buff = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "apply_generated_buff_on_use")
    held["params"]["effectGroupId"] = "missing"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["deletable"]["callIds"] == []
    fixed = deepcopy(held)
    fixed["params"]["effectGroupId"] = "witness"
    expected = apply_repair_patch(doc, {"note": "choose existing utility", "callsUpsert": [fixed]})
    incoming = {"note": "retarget only", "realizationReplacement": doc["realization"],
                "callsUpsert": [fixed], "callIdsDelete": [held["id"], buff["id"]]}
    repaired, _ = _offline_gameplay_repair(monkeypatch, doc, incoming, format_mode)
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("case", ["broken-active", "nonempty-held", "empty-held"])
def test_selector_noop_remains_red_without_host_design(monkeypatch, format_mode, case):
    from infini_local.core.errors import PlannerUnavailable
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = _groups() if case == "broken-active" else build_capability_witness("refresh_generated_effect_group_while_held")
    if case == "broken-active":
        doc["runtimeProgram"]["bindings"].pop()
        doc["runtimeProgram"]["bindings"][0]["usePolicy"]["action"]["effectGroupId"] = "missing"
    elif case == "nonempty-held":
        next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "refresh_generated_effect_group_while_held")["params"]["effectGroupId"] = "missing"
    else:
        doc["runtimeProgram"]["calls"] = [row for row in doc["runtimeProgram"]["calls"] if row["fn"] != "apply_generated_buff_on_use"]
    before = deepcopy(doc)
    with pytest.raises(PlannerUnavailable):
        _offline_gameplay_repair(monkeypatch, doc,
            {"note": "no correction or removal chosen", "realizationReplacement": doc["realization"]}, format_mode)
    assert doc == before
    assert not validate_runtime_program(doc)["ok"]


# Combined binding lanes retain the same canonical compiler/receipt/Repair owners.
def _chance_groups(chance=35):
    doc = _groups()
    for binding in doc["runtimeProgram"]["bindings"]:
        binding["usePolicy"].update(stackCost=1, stackConsumeChancePercent=chance)
    # Deliberately reverse the source order: receipts must resolve exact IDs,
    # not assume source and sorted final binding coordinates agree.
    doc["runtimeProgram"]["bindings"].reverse()
    return doc


@pytest.mark.parametrize("chance", [0, 35, 100])
def test_named_effect_selection_and_stack_probability_compile_independently(chance):
    from infini_local.core.runtime_authoring.technical_lowering import STACK_CHANCE_LOWERER_ID

    doc = _chance_groups(chance)
    before = deepcopy(doc)
    final = compile_runtime_program(doc)
    assert validate_runtime_wire(final)["ok"] and doc == before
    bindings = final["runtimeProgram"]["bindings"]
    assert {b["input"]: (b["usePolicy"]["action"]["effectGroupId"], b["usePolicy"]["stackConsumeChancePercent"])
            for b in bindings} == {"primary_use": ("first", chance), "alternate_use": ("second", chance)}
    assert [(g["id"], g["healLife"], g["healMana"]) for g in final["runtimeProgram"]["effectGroups"]] == [
        ("first", 20, 0), ("second", 0, 35)]
    rows = final["runtimeContract"]["finalWireReceipts"]
    assert sum(r.get("lowererId") == STACK_CHANCE_LOWERER_ID for r in rows) == 2
    assert sum(r.get("lowererId") == EFFECT_GROUP_BINDING_LOWERER_ID for r in rows) == 2
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=final)["ok"]
    assert audit_compiler_receipts(rows, final_document=final)["ok"]
    # Adding probability must not rewrite any pre-existing grouped projection.
    omitted = deepcopy(doc)
    for binding in omitted["runtimeProgram"]["bindings"]:
        del binding["usePolicy"]["stackConsumeChancePercent"]
    expected = compile_runtime_program(omitted)
    for binding in bindings:
        del binding["usePolicy"]["stackConsumeChancePercent"]
    final["runtimeContract"]["finalWireReceipts"] = [r for r in rows if r.get("lowererId") != STACK_CHANCE_LOWERER_ID]
    final["runtimeContract"]["technicalLoweringAudit"]["lowerers"] = [
        r for r in final["runtimeContract"]["technicalLoweringAudit"]["lowerers"] if r["id"] != STACK_CHANCE_LOWERER_ID]
    assert final == expected


@pytest.mark.parametrize("lane", ["chance", "group"])
@pytest.mark.parametrize("attack", ["missing", "duplicate", "coherent-value", "source-identity"])
def test_combined_binding_receipts_authenticate_each_independent_lane(lane, attack):
    from infini_local.core.runtime_authoring.technical_lowering import STACK_CHANCE_LOWERER_ID

    doc = _chance_groups()
    final = compile_runtime_program(doc)
    rows = deepcopy(final["runtimeContract"]["finalWireReceipts"])
    lowerer = STACK_CHANCE_LOWERER_ID if lane == "chance" else EFFECT_GROUP_BINDING_LOWERER_ID
    claim = next(r for r in rows if r.get("lowererId") == lowerer)
    if attack == "missing":
        rows.remove(claim)
    elif attack == "duplicate":
        rows.append(deepcopy(claim))
    elif attack == "coherent-value":
        value = 99 if lane == "chance" else "second" if claim["value"] == "first" else "first"
        claim["value"] = value
        binding = final["runtimeProgram"]["bindings"][int(claim["finalPath"].split("[")[1].split("]")[0])]
        if lane == "chance":
            binding["usePolicy"]["stackConsumeChancePercent"] = value
        else:
            binding["usePolicy"]["action"]["effectGroupId"] = value
    else:
        source_index = int(claim["authoredPaths"][0].split("[")[1].split("]")[0])
        doc["runtimeProgram"]["bindings"][source_index]["id"] = "changed_source_binding"
        assert validate_runtime_program(doc)["ok"]
    assert not audit_compiler_receipts(rows, authored_document=doc, final_document=final)["ok"]
    if attack in {"missing", "duplicate"}:
        assert not audit_compiler_receipts(rows, final_document=final)["ok"]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("chance", [None, 0, 35, 100])
def test_combined_provider_preparation_preserves_presence_and_exact_compilation(monkeypatch, format_mode, chance):
    import json
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract
    from infini_local.pipelines import llm_authoring_pipeline as author
    from infini_local.pipelines import llm_transport as transport
    from test_codex_subscription_contract import _encode_nullable_fixture

    doc = _chance_groups(chance)
    if chance is None:
        for binding in doc["runtimeProgram"]["bindings"]:
            del binding["usePolicy"]["stackConsumeChancePercent"]
    before = json.dumps(doc, sort_keys=True)
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    request, user, system = author.build_initial_author_request({}, {}, {}, {}, "combined-offline", model_name="offline-no-model")
    assert [(row["role"], row["content"]) for row in request["messages"]] == [("system", system), ("user", user)]
    local = contract.author_item_response_schema()
    payload = _encode_nullable_fixture(doc, local) if format_mode == "json_schema" else deepcopy(doc)
    if format_mode == "json_schema":
        Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(payload)
    parsed = author._prepare_parsed_author_item(json.loads(json.dumps(payload)), response_format=request["response_format"])
    assert json.dumps(parsed, sort_keys=True) == before
    final = compile_runtime_program(parsed)
    assert final == compile_runtime_program(doc) and validate_runtime_wire(final)["ok"]
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("invalid_leaf", ["chance", "group", "input"])
def test_combined_real_frozen_repair_preserves_the_other_binding_lanes(monkeypatch, format_mode, invalid_leaf):
    import json
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = _chance_groups()
    binding = doc["runtimeProgram"]["bindings"][0]
    binding_id = binding["id"]
    expected = deepcopy(doc)
    if invalid_leaf == "chance":
        binding["usePolicy"]["stackConsumeChancePercent"] = 101
        path = "usePolicy.stackConsumeChancePercent"
    elif invalid_leaf == "group":
        binding["usePolicy"]["action"]["effectGroupId"] = "missing"
        path = "usePolicy.action.effectGroupId"
    else:
        binding["input"] = []
        path = "input"
    before = json.dumps(doc, sort_keys=True)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["bindings"] == [{"id": binding_id, "paths": [path]}]
    corrected = deepcopy(expected["runtimeProgram"]["bindings"][0])
    corrected["usePolicy"]["contactDamage"] = True
    if invalid_leaf != "chance":
        corrected["usePolicy"]["stackConsumeChancePercent"] = 99
    if invalid_leaf != "group":
        corrected["usePolicy"]["action"]["effectGroupId"] = "first"
    if invalid_leaf != "input":
        corrected["input"] = "primary_use"
    incoming = {"note": "explicit exact leaf only", "realizationReplacement": doc["realization"], "bindingsUpsert": [corrected]}
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, incoming, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["bindings"] == scope["fieldPermissions"]["bindings"]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("input_value", [[], {}, None, True, 1, "PRIMARY_USE"])
def test_combined_raw_wire_malformed_input_is_structured_nonmutating_refusal(input_value):
    import json

    final = compile_runtime_program(_chance_groups())
    final.pop("runtimeContract")
    final["runtimeProgram"]["bindings"][0]["input"] = deepcopy(input_value)
    raw = json.dumps(final, sort_keys=True)
    parsed = json.loads(raw)
    report = validate_runtime_wire(parsed)
    assert not report["ok"]
    assert any(e["code"] == "unknown_runtime_input" for e in report["errors"])
    assert json.dumps(parsed, sort_keys=True) == raw
