"""Offline presence-sensitive generated-buff policy, authenticated source and Repair."""

from copy import deepcopy
import json
from typing import Any

import pytest

from repair_test_helpers import gameplay_repair, provider_roundtrip
from infini_local.core import llm_config
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
from infini_local.pipelines import llm_authoring_pipeline as author

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness

FN = "apply_generated_buff_on_use"


def _fixture():
    doc = build_capability_witness(FN)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN)
    return doc, call


def test_explicit_positive_exhaustion_tracer_preserves_source_and_exact_wire_receipt():
    doc, call = _fixture()
    call["params"]['exhaustionSeconds'] = (180) / 60
    before = json.dumps(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report
    final = json.loads(json.dumps(compile_runtime_program(doc)))
    assert final["gameplay"]["generatedBuff"]["exhaustionTicks"] == 180
    assert type(final["gameplay"]["generatedBuff"]["exhaustionTicks"]) is int
    receipts = final["runtimeContract"]["finalWireReceipts"]
    policy = [r for r in receipts if r["finalPath"] == "gameplay.generatedBuff.exhaustionTicks"]
    index = doc["runtimeProgram"]["calls"].index(call)
    assert policy == [{"callId": call["id"], "fn": FN,
                       "authoredPath": f"runtimeProgram.calls[{index}].params.exhaustionSeconds",
                       "finalPath": "gameplay.generatedBuff.exhaustionTicks",
                       "value": 180, "status": "delivered"}]
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=final)["ok"]
    assert validate_runtime_wire(final)["ok"]
    assert json.dumps(doc) == before


OMITTED = "omitted"


def _policy_fixture(value: Any = OMITTED, group=None):
    doc, call = _fixture()
    if value != OMITTED:
        call["params"]['exhaustionSeconds'] = value / 60 if type(value) in (int, float) else value
    if group is not None:
        call["params"]["effectGroupId"] = group
        doc["runtimeProgram"]["bindings"][0]["action"]["effectGroupId"] = group
    return doc, call


def _buff(final, group=None):
    owner = final["gameplay"] if group is None else next(
        row for row in final["runtimeProgram"]["effectGroups"] if row["id"] == group)
    return owner["generatedBuff"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("group", [None, "survey"])
@pytest.mark.parametrize("value", [OMITTED, 0, 1, 21600])
def test_serialized_author_presence_policy_and_registered_card(monkeypatch, mode, group, value):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = author.build_initial_author_request({}, {}, "policy", model_name="offline")
    request = json.loads(json.dumps(request))
    card = next(c for c in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == FN)
    spec = CAPABILITY_REGISTRY[FN].params["exhaustionSeconds"]
    assert not spec.required and spec.default is None and spec.neutral is None
    param = card["params"]['exhaustionSeconds']
    assert param["type"] == "number" and param["min"] == 0 and param["max"] == 360
    assert "default" not in param and "neutral" not in param
    doc, _ = _policy_fixture(value, group)
    doc = {key: doc[key] for key in ("name", "category", "runtimeProgram")}
    restored = provider_roundtrip(doc, request["response_format"])
    assert validate_runtime_program(restored)["ok"]
    final = json.loads(json.dumps(compile_runtime_program(restored)))
    buff = _buff(final, group)
    assert ("exhaustionTicks" in buff) == (value != OMITTED)
    if value != OMITTED:
        assert type(buff["exhaustionTicks"]) is int and buff["exhaustionTicks"] == value
    rows = final["runtimeContract"]["finalWireReceipts"]
    assert sum(r["finalPath"].endswith(".exhaustionTicks") for r in rows) == (value != OMITTED)
    declared = next(r for r in final["runtimeContract"]["technicalLoweringAudit"]["lowerers"]
                    if r["id"] == "item_fields_to_tml_projection")["outputs"]
    # Registry audit declares the current allowed surface, not present leaves.
    # Presence and the exact receipt are checked independently above.
    assert "gameplay.generatedBuff.exhaustionTicks" in declared
    assert validate_runtime_wire(final)["ok"]
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=final)["ok"]
    final.pop("runtimeContract")
    assert validate_runtime_wire(final)["ok"]  # Delivery DTO intentionally strips provenance.


@pytest.mark.parametrize("group", [None, "survey"])
@pytest.mark.parametrize("value", [None, True, False, 0.1, "180", -1, 21601])
def test_present_invalid_policy_is_rejected_by_real_parse_author_and_strict_wire(group, value):
    doc, call = _policy_fixture(value, group)
    parsed = author._prepare_parsed_author_item(json.loads(json.dumps(doc)), response_format={"type": "json_object"})
    assert "exhaustionSeconds" in next(c for c in parsed["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]
    report = validate_runtime_program(parsed)
    assert not report["ok"], report
    scope = build_runtime_repair_scope(parsed, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ['params.exhaustionSeconds']}]
    with pytest.raises(ValueError):
        compile_runtime_program(parsed)
    good, _ = _policy_fixture(180, group)
    final = compile_runtime_program(good)
    final.pop("runtimeContract")
    _buff(final, group)["exhaustionTicks"] = value
    report = validate_runtime_wire(json.loads(json.dumps(final)))
    assert not report["ok"]
    assert any(e["path"].endswith(".exhaustionTicks") for e in report["errors"])


@pytest.mark.parametrize("group", [None, "survey"])
def test_exhaustion_policy_alone_never_counts_as_an_executable_buff_effect(group):
    doc, call = _policy_fixture(180, group)
    for name, spec in CAPABILITY_REGISTRY[FN].params.items():
        if spec.neutral is not None:
            call["params"][name] = deepcopy(spec.neutral)
    assert not CAPABILITY_REGISTRY[FN].has_non_neutral_effect(call["params"])
    assert not validate_runtime_program(doc)["ok"]
    good, _ = _policy_fixture(180, group)
    final = compile_runtime_program(good)
    buff = _buff(final, group)
    for name, spec in CAPABILITY_REGISTRY[FN].params.items():
        if spec.neutral is not None:
            buff[spec.wire_name or name] = spec.to_wire(spec.neutral)
    final.pop("runtimeContract")
    assert not validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("value", [OMITTED, 0, 180])
def test_repair_unrelated_leaf_freezes_accepted_policy_value_or_absence(monkeypatch, mode, value):
    doc, call = _policy_fixture(value, "survey")
    expected = deepcopy(doc)
    call["params"]['durationSeconds'] = True
    candidate = deepcopy(call)
    candidate["params"]['durationSeconds'] = next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]['durationSeconds']
    if value == 180:
        candidate["params"].pop("exhaustionSeconds")  # Repair omission is no-change.
    else:
        candidate["params"]['exhaustionSeconds'] = (90) / 60  # Frozen zero/absence cannot be rewritten.
    candidate["params"]["effectGroupId"] = "foreign"
    repaired, dossier = gameplay_repair(monkeypatch, doc, {"note": "duration only", "callsUpsert": [candidate],
        "realizationReplacement": doc["realization"]}, mode)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ['params.durationSeconds']}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    final = compile_runtime_program(repaired)
    assert validate_runtime_wire(final)["ok"]
    assert ("exhaustionTicks" in _buff(final, "survey")) == (value != OMITTED)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_policy_type_only_repair_changes_exact_leaf_and_freezes_duration_group_stats(monkeypatch, mode):
    doc, call = _policy_fixture(True, "survey")
    expected = deepcopy(doc)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]['exhaustionSeconds'] = (1) / 60
    candidate = deepcopy(call)
    candidate["params"].update(exhaustionSeconds=(1) / 60, durationSeconds=(1) / 60, effectGroupId="foreign", lightStrength=1.5)
    repaired, dossier = gameplay_repair(monkeypatch, doc, {"note": "typed policy leaf", "callsUpsert": [candidate],
        "realizationReplacement": doc["realization"]}, mode)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ['params.exhaustionSeconds']}]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert _buff(compile_runtime_program(repaired), "survey")["exhaustionTicks"] == 1


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_invalid_policy_cannot_be_repaired_by_omission_or_defaults(monkeypatch, mode):
    doc, call = _policy_fixture(-1)
    candidate = deepcopy(call)
    candidate["params"].pop("exhaustionSeconds")
    with pytest.raises(PlannerUnavailable, match="could not be deterministically filtered"):
        gameplay_repair(monkeypatch, doc, {"note": "omission is not correction", "callsUpsert": [candidate],
            "realizationReplacement": doc["realization"]}, mode)
    assert call["params"]['exhaustionSeconds'] == -1 / 60


def _two_groups():
    doc, first = _policy_fixture(180, "first")
    second = deepcopy(first)
    second.update(id="second_policy")
    second["params"]["effectGroupId"] = "second"
    doc["runtimeProgram"]["calls"].append(second)
    binding = deepcopy(doc["runtimeProgram"]["bindings"][0])
    binding.update(id="alternate_policy", input="alternate_use")
    binding["action"]["effectGroupId"] = "second"
    doc["runtimeProgram"]["bindings"].append(binding)
    return doc


@pytest.mark.parametrize("attack", ["value", "call", "coordinate", "group", "coherent-group", "missing", "duplicate", "status", "delete-both", "remove-all"])
def test_existing_receipts_authenticate_exact_policy_value_call_and_group(attack):
    doc = _two_groups()
    final = json.loads(json.dumps(compile_runtime_program(doc)))
    rows = final["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in rows if r["finalPath"] == "runtimeProgram.effectGroups[0].generatedBuff.exhaustionTicks")
    other = next(r for r in rows if r["finalPath"] == "runtimeProgram.effectGroups[1].generatedBuff.exhaustionTicks")
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=final)["ok"]
    if attack == "value":
        _buff(final, "first")["exhaustionTicks"] = row["value"] = 181
    elif attack == "call":
        row["callId"] = other["callId"]
    elif attack == "coordinate":
        row["authoredPath"] = other["authoredPath"]
    elif attack == "group":
        row["finalPath"], other["finalPath"] = other["finalPath"], row["finalPath"]
    elif attack == "coherent-group":
        # Swap complete receipt owners, not just the policy leaf. This is a
        # coherent persisted claim, but contradicts both original source groups.
        for receipt in rows:
            if receipt.get("fn") != FN:
                continue
            index = 1 if receipt["finalPath"].startswith("runtimeProgram.effectGroups[0].") else 0
            receipt["finalPath"] = receipt["finalPath"].replace(f"effectGroups[{1 - index}]", f"effectGroups[{index}]")
            if receipt["finalPath"].endswith(".id"):
                receipt["value"] = final["runtimeProgram"]["effectGroups"][index]["id"]
    elif attack == "missing":
        rows.remove(row)
    elif attack == "duplicate":
        rows.append(deepcopy(row))
    elif attack == "status":
        row["status"] = "declared_neutral_omission"
    elif attack == "delete-both":
        rows.remove(row)
        _buff(final, "first").pop("exhaustionTicks")
    else:
        rows[:] = [r for r in rows if r.get("fn") != FN]
    report = audit_compiler_receipts(rows, authored_document=doc, final_document=final)
    assert not report["ok"], report
    if attack in {"group", "missing", "duplicate", "status", "remove-all"}:
        assert not audit_compiler_receipts(rows, final_document=final)["ok"]
        assert not validate_runtime_wire(final)["ok"]
    if attack in {"value", "coherent-group", "delete-both"}:
        # Internally coherent wire cannot authenticate an unavailable Author.
        wire_only = audit_compiler_receipts(rows, final_document=final)
        assert wire_only["ok"] and not wire_only["authoredSourceChecked"]


@pytest.mark.parametrize("value", [0, 180])
def test_policy_wire_presence_demands_receipts_even_when_all_capability_rows_are_removed(value):
    doc, _ = _policy_fixture(value)
    final = compile_runtime_program(doc)
    rows = final["runtimeContract"]["finalWireReceipts"]
    rows[:] = [r for r in rows if r.get("fn") != FN]
    report = audit_compiler_receipts(rows, final_document=final)
    assert not report["ok"], report
    assert not validate_runtime_wire(final)["ok"]
    final.pop("runtimeContract")
    assert validate_runtime_wire(final)["ok"]  # No provenance claim on stripped DTO.


def test_current_absent_policy_recompiles_without_hidden_backfill_or_private_baseline():
    doc, call = _policy_fixture()
    source = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    first = compile_runtime_program(doc)
    second = compile_runtime_program(json.loads(source))
    assert first == second
    assert "exhaustionSeconds" not in call["params"]
    assert "exhaustionTicks" not in _buff(first)
    assert not any(row["finalPath"].endswith(".exhaustionTicks")
                   for row in first["runtimeContract"]["finalWireReceipts"])
    assert validate_runtime_wire(first)["ok"]
    assert audit_compiler_receipts(first["runtimeContract"]["finalWireReceipts"],
                                   authored_document=doc, final_document=first)["ok"]
    assert json.dumps(doc, ensure_ascii=False, separators=(",", ":")) == source


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("first,second", [(OMITTED, 0), (0, 180), (180, OMITTED)])
def test_default_and_named_policies_are_independently_authored_not_inferred(monkeypatch, mode, first, second):
    doc = _two_groups()
    for call, value in zip([c for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN], [first, second]):
        call["params"].pop("exhaustionSeconds")
        if value != OMITTED:
            call["params"]['exhaustionSeconds'] = value / 60 if type(value) in (int, float) else value
    primary = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN)
    primary["params"].pop("effectGroupId")
    doc["runtimeProgram"]["bindings"][0]["action"].pop("effectGroupId")
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = author.build_initial_author_request({}, {}, "mixed-policy", model_name="offline")
    doc = {key: doc[key] for key in ("name", "category", "runtimeProgram")}
    doc = provider_roundtrip(doc, request["response_format"])
    final = compile_runtime_program(doc)
    for group, value in [(None, first), ("second", second)]:
        buff = _buff(final, group)
        assert ("exhaustionTicks" in buff) == (value != OMITTED)
        if value != OMITTED:
            assert type(buff["exhaustionTicks"]) is int and buff["exhaustionTicks"] == value
    assert validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_provider_null_scaffolding_is_only_optional_omission_not_authored_null(monkeypatch, mode):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_response_schema
    from test_codex_subscription_contract import _encode_nullable_fixture

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = author.build_initial_author_request({}, {}, "policy-null", model_name="offline")
    doc, call = _policy_fixture(None)
    assert not validate_runtime_program(doc)["ok"]
    if mode == "json_schema":
        good, _ = _policy_fixture()
        good = {key: good[key] for key in ("name", "category", "runtimeProgram")}
        local = author_item_response_schema()
        payload = _encode_nullable_fixture(good, local)
        assert next(c for c in payload["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]['exhaustionSeconds'] is None
        Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(payload)
        restored = author._prepare_parsed_author_item(json.loads(json.dumps(payload)), response_format=request["response_format"])
        restored_call = next(c for c in restored["runtimeProgram"]["calls"] if c["id"] == call["id"])
        assert "exhaustionSeconds" not in restored_call["params"]
        assert validate_runtime_program(restored)["ok"]
        assert "exhaustionTicks" not in _buff(compile_runtime_program(restored))
    else:
        restored = author._prepare_parsed_author_item(doc, response_format=request["response_format"])
        assert not validate_runtime_program(restored)["ok"]


@pytest.mark.parametrize("value", [True, False, "180", -1, 361])
def test_serialized_strict_provider_rejects_bad_policy_tokens(monkeypatch, value):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_response_schema
    from test_codex_subscription_contract import _encode_nullable_fixture

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    request, _, _ = author.build_initial_author_request({}, {}, "policy-typed", model_name="offline")
    doc, call = _policy_fixture(180)
    payload = _encode_nullable_fixture(doc, author_item_response_schema())
    next(c for c in payload["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]['exhaustionSeconds'] = value
    assert not Draft202012Validator(request["response_format"]["json_schema"]["schema"]).is_valid(payload)
    restored = author._prepare_parsed_author_item(json.loads(json.dumps(payload)), response_format=request["response_format"])
    assert not validate_runtime_program(restored)["ok"]


def test_explicit_held_refresh_preserves_policy_on_its_exact_generated_group():
    doc = build_capability_witness("refresh_generated_effect_group_while_held")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN)
    call["params"]['exhaustionSeconds'] = (180) / 60
    before = json.dumps(doc)
    final = compile_runtime_program(doc)
    assert _buff(final, "witness")["exhaustionTicks"] == 180
    assert final["runtimeProgram"]["heldEffectGroupId"] == "witness"
    assert validate_runtime_wire(final)["ok"]
    assert json.dumps(doc) == before


@pytest.mark.parametrize("group", [None, "survey"])
@pytest.mark.parametrize("value", [0, 180])
def test_sparse_wire_policy_requires_provenance_without_historical_neutral_slots(group, value):
    doc, _ = _policy_fixture(value, group)
    final = compile_runtime_program(doc)
    buff = _buff(final, group)
    for name, spec in CAPABILITY_REGISTRY[FN].params.items():
        if spec.neutral is not None and name != "lightStrength":
            buff.pop(spec.wire_name or name, None)
    rows = final["runtimeContract"]["finalWireReceipts"]
    rows[:] = [r for r in rows if r.get("fn") != FN]
    # Strip only internal compiler provenance for the independent positive DTO.
    delivery = deepcopy(final)
    delivery.pop("runtimeContract")
    assert validate_runtime_wire(delivery)["ok"]
    report = audit_compiler_receipts(rows, final_document=final)
    assert not report["ok"], report
    assert not validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("group", [None, "survey"])
def test_coherent_inserted_zero_policy_cannot_forge_accepted_source_absence(group):
    doc, call = _policy_fixture(group=group)
    final = compile_runtime_program(doc)
    _buff(final, group)["exhaustionTicks"] = 0
    rows = final["runtimeContract"]["finalWireReceipts"]
    source_index = doc["runtimeProgram"]["calls"].index(call)
    prefix = "gameplay" if group is None else "runtimeProgram.effectGroups[0]"
    rows.append({"fn": FN, "callId": call["id"], "authoredPath": f"runtimeProgram.calls[{source_index}].params.exhaustionSeconds",
                 "finalPath": prefix + ".generatedBuff.exhaustionTicks", "value": 0, "status": "delivered"})
    report = audit_compiler_receipts(rows, authored_document=doc, final_document=final)
    assert not report["ok"] and any("absent" in r["reason"] for r in report["violations"])
    report = audit_compiler_receipts(rows, final_document=final)
    assert report["ok"] and not report["authoredSourceChecked"]
