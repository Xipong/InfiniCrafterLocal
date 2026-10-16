"""Offline transactions shared by frozen Repair observers, not alternative contracts."""
from copy import deepcopy
import json
import socket

import pytest
from jsonschema import Draft202012Validator

from prompt_packet_helpers import request_dossier
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.binding_use_policy import action_kind
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines import author_item_contract as contract
from infini_local.pipelines import llm_authoring_pipeline as author, llm_transport as transport
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_codex_subscription_contract import _encode_nullable_fixture


DELETE = object()


def edit_fields(row, edits):
    """Apply explicit case data; omission is never a synthesized default."""
    for path, value in edits.items():
        parts = path.split(".")
        target = row
        for key in parts[:-1]:
            target = target.setdefault(key, {})
        if value is DELETE:
            target.pop(parts[-1], None)
        else:
            target[parts[-1]] = deepcopy(value)


def offline_builder(monkeypatch, format_mode, respond):
    def no_network(*args, **kwargs):
        raise AssertionError("live network forbidden in offline Repair tests")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    for name, value in {
        "USE_LLM": True, "resolve_llm_model": lambda: "offline-no-model",
        "llm_chat_json": respond, "trace_event": lambda *a, **kw: None,
        "trace_stage_request": lambda *a, **kw: None,
        "llm_reasoning_system_suffix": lambda *a, **kw: "",
        "apply_llm_common_options": lambda request, **kw: request,
    }.items():
        monkeypatch.setattr(author, name, value)


def repair_with_response(monkeypatch, doc, incoming, format_mode, *, out_of_scope_response=False,
                         invalid_report=False):
    """Only provider I/O is replaced: request, parser, scope, merge and admission are real."""
    requests = []

    def respond(request, **kwargs):
        requests.append(deepcopy(request))
        assert request["response_format"]["type"] == format_mode
        payload = deepcopy(incoming)
        if format_mode == "json_schema":
            payload = _encode_nullable_fixture(payload, contract.author_item_repair_response_schema())
            validator = Draft202012Validator(request["response_format"]["json_schema"]["schema"])
            if invalid_report:
                if "realizationReplacement" not in incoming:
                    payload.pop("realizationReplacement")
                assert not validator.is_valid(payload)
            elif out_of_scope_response:
                # Foreign hostile rows retain their literal sparse shape. They are
                # not nullable scaffolding offered by the request-local grammar.
                scope = request_dossier(request)["repairScope"]
                mutable_ids = {row["id"] for row in scope["fieldPermissions"]["calls"]}
                payload["callsUpsert"] = [
                    encoded if original["id"] in mutable_ids else deepcopy(original)
                    for original, encoded in zip(incoming["callsUpsert"], payload["callsUpsert"])
                ]
                assert not validator.is_valid(payload)
            else:
                validator.validate(payload)
        return {"choices": [{"message": {"content": json.dumps(payload)}}],
                "_debug": {"responseFormatType": format_mode}}

    offline_builder(monkeypatch, format_mode, respond)
    try:
        result = author.repair_author_item_after_failure(
            doc, {}, {}, "offline-only", failure_report=validate_runtime_program(doc))
    finally:
        if invalid_report:
            assert len(requests) == 1
    assert len(requests) == 1
    return result, requests[0]


def gameplay_repair(monkeypatch, doc, incoming, format_mode, **kwargs):
    result, request = repair_with_response(monkeypatch, doc, incoming, format_mode, **kwargs)
    return result, request_dossier(request)


def frozen_gameplay_repair(monkeypatch, doc, incoming, mode, permissions, expected, **kwargs):
    """Observe the real request and frozen whole-source closure, then exact delivery."""
    before = json.dumps(doc, sort_keys=True)
    repaired, dossier = gameplay_repair(monkeypatch, doc, incoming, mode, **kwargs)
    for owner, rows in permissions.items():
        assert dossier["repairScope"]["fieldPermissions"][owner] == rows
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    final = assert_repaired_source(repaired, expected)
    assert json.dumps(doc, sort_keys=True) == before
    return repaired, dossier, final


def provider_roundtrip(doc, response_format):
    """Serialize the supplied literal shape through the actual provider inverse."""
    before = json.dumps(doc, sort_keys=True)
    payload = deepcopy(doc)
    if response_format["type"] == "json_schema":
        payload = _encode_nullable_fixture(payload, contract.author_item_response_schema())
        Draft202012Validator(response_format["json_schema"]["schema"]).validate(payload)
    restored = author._prepare_parsed_author_item(
        json.loads(json.dumps(payload)), response_format=response_format)
    assert json.dumps(restored, sort_keys=True) == before
    assert json.dumps(doc, sort_keys=True) == before
    return restored


def frozen_call_repair(doc, incoming, permissions, expected, *, note):
    """Exercise exact local scope/filter/apply, without manufacturing candidate fields."""
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope

    before = json.dumps(doc, sort_keys=True)
    report = validate_runtime_program(doc)
    assert not report["ok"], report
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == permissions
    patch, audit = filter_repair_patch_scope(doc, {"note": note, "callsUpsert": incoming}, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    repaired = apply_repair_patch(doc, patch)
    final = assert_repaired_source(repaired, expected)
    assert json.dumps(doc, sort_keys=True) == before
    return repaired, final


def assert_delivery(doc):
    final = compile_runtime_program(doc)
    assert validate_runtime_wire(final)["ok"]
    return final


def assert_repaired_source(repaired, expected):
    repaired.pop("debug", None)
    # JSON equality distinguishes bool/int, int/float and exact optional presence.
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    return assert_delivery(repaired)


def binding_case(case):
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
    elif case == "pure-placement":
        doc = build_capability_witness("configure_tile_placement")
    else:
        assert case == "placement"
        doc = build_runtime_fixture("fishing_platform_tool")
    row = next(row for row in doc["runtimeProgram"]["bindings"]
               if (row["input"] == case if case in {"equipped", "hold"}
                   else action_kind(row) == {"body": "use_item_body", "effects": "apply_item_effects",
                                             "placement": "place_item", "pure-placement": "place_item"}[case]))
    return doc, row


def explicit_binding(doc, row):
    result = deepcopy(row)
    kind = action_kind(row)
    result.setdefault("action", {})["kind"] = kind
    if kind != "spawn_entity":
        result["action"]["targetId"] = next(e["id"] for e in doc["runtimeProgram"]["entities"]
                                             if e["kind"] == "item_body")
    if row["input"] in {"equipped", "hold"} or kind == "place_item":
        result.update(stackCost=1 if kind == "place_item" else 0, contactDamage=False)
    return result


class BindingTransaction:
    """A valid control and separate broken source/candidate, preserving sparse facts."""
    def __init__(self, case, *, explicit=False, body_id=None, group=None, values=None):
        self.doc, self.row = binding_case(case)
        if body_id is not None:
            old_id = self.doc["runtimeProgram"]["entities"][0]["id"]
            self.doc["runtimeProgram"]["entities"][0]["id"] = body_id
            if self.doc["runtimeProgram"]["primaryEntityId"] == old_id:
                self.doc["runtimeProgram"]["primaryEntityId"] = body_id
        if explicit:
            self.row.update(explicit_binding(self.doc, self.row))
        if group is not None:
            self.row.setdefault("action", {})["effectGroupId"] = group
            next(c for c in self.doc["runtimeProgram"]["calls"]
                 if c["fn"] == "move_player_on_use")["params"]["effectGroupId"] = group
        edit_fields(self.row, values or {})
        self.expected = deepcopy(self.doc)
        self.candidate = deepcopy(self.row)

    def repair(self, monkeypatch, mode, *, paths, ignored=False, create=None, permissions=None):
        before = json.dumps(self.doc, sort_keys=True)
        assert_delivery(self.expected)  # independently valid, unfiltered control
        repaired, dossier = gameplay_repair(monkeypatch, self.doc, {
            "note": "explicit exact transaction correction; valid siblings stay frozen",
            "realizationReplacement": self.doc["realization"], "bindingsUpsert": [self.candidate],
        }, mode)
        scope = dossier["repairScope"]
        assert scope["fieldPermissions"]["bindings"] == (permissions if permissions is not None else [{"id": self.row["id"], "paths": paths}])
        self.audit = deepcopy(repaired["debug"]["gameplayRepairFilterAudit"])
        if create is not None:
            assert scope["create"]["bindings"]["allowed"] is create
        if ignored:
            assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
        final = assert_repaired_source(repaired, self.expected)
        expected_row = next(b for b in self.expected["runtimeProgram"]["bindings"] if b["id"] == self.row["id"])
        wire_row = next(b for b in final["runtimeProgram"]["bindings"] if b["id"] == self.row["id"])
        # Independent literal expectations: source equality alone cannot prove lowering.
        input_name = expected_row["input"]
        kind = expected_row.get("action", {}).get("kind", "spawn_entity" if input_name == "hold" else "equip_passive")
        target = expected_row.get("action", {}).get("targetId", next(
            e["id"] for e in self.expected["runtimeProgram"]["entities"] if e["kind"] == "item_body"))
        policy = wire_row["usePolicy"]
        assert wire_row["input"] == input_name
        assert policy["action"]["kind"] == kind and policy["action"]["targetId"] == target
        cost = expected_row.get("stackCost", 1 if kind == "place_item" else 0)
        assert type(policy["stackCost"]) is int and policy["stackCost"] == cost
        assert policy["contactDamage"] is expected_row.get("contactDamage", False)
        assert ("stackConsumeChancePercent" in policy) == ("stackConsumeChancePercent" in expected_row)
        if "stackConsumeChancePercent" in expected_row:
            assert type(policy["stackConsumeChancePercent"]) is int
            assert policy["stackConsumeChancePercent"] == expected_row["stackConsumeChancePercent"]
        assert policy["action"].get("effectGroupId") == expected_row.get("action", {}).get("effectGroupId")
        assert json.dumps(self.doc, sort_keys=True) == before
        return repaired, dossier, final


@pytest.fixture
def binding_transaction():
    return BindingTransaction
