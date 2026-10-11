"""Current Author notation: one source admission/compiler/Repair boundary."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, compile_runtime_program, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.capability_registry import visible_capabilities
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _explicit_calls(source):
    """Render only the two exact existing omission branches, without editing fixtures."""
    out = deepcopy(source)
    body = next(row["id"] for row in out["runtimeProgram"]["entities"] if row["kind"] == "item_body")
    for call in out["runtimeProgram"]["calls"]:
        cap = CAPABILITY_REGISTRY[call["fn"]]
        if cap.target_kinds == ("item_body",):
            call["target"] = body
        if not cap.params:
            call["params"] = {}
    return out


@pytest.mark.parametrize("fn", [cap.name for cap in visible_capabilities()])
def test_registry_calls_share_explicit_envelope_without_changing_wire_or_receipts(fn):
    from jsonschema import Draft202012Validator
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    from infini_local.pipelines.author_item_contract import author_item_response_schema
    import json
    sparse = build_capability_witness(fn)
    sparse_before = deepcopy(sparse)
    source = _explicit_calls(sparse)
    before = deepcopy(source)
    assert all(set(call) == {"id", "fn", "target", "params"} for call in source["runtimeProgram"]["calls"])
    assert Draft202012Validator(author_item_response_schema()).is_valid(source)
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    assert json.dumps(wire, ensure_ascii=False) == json.dumps(compile_runtime_program(sparse), ensure_ascii=False), "Exact serialized executable wire AND receipts remain unchanged"
    assert sparse == sparse_before
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    for authored in (sparse, source):
        assert audit_compiler_receipts(receipts, authored_document=authored, final_document=wire)["ok"]
    assert source == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("fn", ["configure_accessory", "set_projectile_lifetime", "move_straight"])
def test_provider_roundtrip_preserves_sparse_and_explicit_envelope_branches(monkeypatch, mode, fn):
    import json
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_response_schema, project_provider_author_item_to_local
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    from test_codex_subscription_contract import _encode_nullable_fixture
    # Heavy serialized observers cover each distinct branch, not the registry x format product.
    shapes = {(cap.target_kinds == ("item_body",), bool(cap.params)) for cap in visible_capabilities()}
    assert shapes == {(True, True), (False, True), (False, False)}
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = build_initial_author_request({}, {}, {}, {}, "call-envelope", model_name="offline")
    packet = json.loads(user)
    assert [set(row) for row in packet["requiredJsonShape"]["runtimeProgram"]["calls"]] == [{"id", "fn", "target", "params"}]
    assert "one explicit id/fn/target/params envelope" in packet["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["rowShapes"]
    schema = author_item_response_schema()
    for source in (build_capability_witness(fn), _explicit_calls(build_capability_witness(fn))):
        encoded = _encode_nullable_fixture(source, schema) if mode == "json_schema" else deepcopy(source)
        if mode == "json_schema":
            Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(encoded)
        restored = project_provider_author_item_to_local(encoded, response_format=request["response_format"])
        assert restored == source
        assert validate_runtime_wire(compile_runtime_program(restored))["ok"]


@pytest.mark.parametrize("field,value", [
    pytest.param("target", "missing", id="missing-id"),
    pytest.param("target", "item", id="not-a-literal-item-alias"),
    pytest.param("target", "nail", id="existing-incompatible-projectile"),
    pytest.param("target", "", id="empty-id"),
    pytest.param("target", None, id="null-target"),
    pytest.param("target", [], id="list-target"),
    pytest.param("target", {}, id="object-target"),
    pytest.param("target", True, id="boolean-target"),
    pytest.param("target", 7, id="integer-target"),
    pytest.param("params", None, id="null-params"),
    pytest.param("params", [], id="list-params"),
    pytest.param("params", "", id="string-params"),
    pytest.param("params", True, id="boolean-params"),
    pytest.param("params", 0, id="integer-params"),
    pytest.param("params", {"speed": 1}, id="unknown-noarg-member"),
])
def test_present_call_fields_are_never_ignored(field, value):
    source = _explicit_calls(build_runtime_fixture("workbench_blade"))
    body = next(row for row in source["runtimeProgram"]["entities"] if row["kind"] == "item_body")
    old_id = body["id"]
    body["id"] = "opaque_body"
    for call in source["runtimeProgram"]["calls"]:
        if call["target"] == old_id:
            call["target"] = body["id"]
    if source["runtimeProgram"]["primaryEntityId"] == old_id:
        source["runtimeProgram"]["primaryEntityId"] = body["id"]
    assert validate_runtime_program(source)["ok"], validate_runtime_program(source)
    call = next(row for row in source["runtimeProgram"]["calls"]
                if row["fn"] == ("configure_item_stats" if field == "target" else "move_straight"))
    call[field] = value
    before = deepcopy(source)
    report = validate_runtime_program(source)
    assert not report["ok"]
    assert any("." + field in row["path"] for row in report["errors"]), report
    with pytest.raises(ValueError):
        compile_runtime_program(source)
    assert source == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_nullable_transport_does_not_erase_invalid_present_call_neighbours(monkeypatch, mode):
    from infini_local.pipelines.author_item_contract import author_item_response_schema, project_provider_author_item_to_local
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    from test_codex_subscription_contract import _encode_nullable_fixture
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = build_initial_author_request({}, {}, {}, {}, "invalid-call-envelope", model_name="offline")
    source = _explicit_calls(build_runtime_fixture("workbench_blade"))
    encoded = _encode_nullable_fixture(source, author_item_response_schema()) if mode == "json_schema" else deepcopy(source)
    noarg = next(row for row in encoded["runtimeProgram"]["calls"] if row["fn"] == "move_straight")
    # Required selectors and unknown null members are authored invalid content, never transport omissions.
    noarg["target"] = None
    noarg["params"] = {"foreign": None}
    stats = next(row for row in encoded["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    stats["params"] = None  # required object, not a nullable optional
    if mode == "json_object":
        stats["target"] = None  # without schema transport, even optional null remains authored
    before = deepcopy(encoded)
    restored = project_provider_author_item_to_local(encoded, response_format=request["response_format"])
    noarg = next(row for row in restored["runtimeProgram"]["calls"] if row["fn"] == "move_straight")
    stats = next(row for row in restored["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    assert noarg["target"] is None and noarg["params"] == {"foreign": None}
    assert stats["params"] is None
    if mode == "json_object":
        assert stats["target"] is None
    assert not validate_runtime_program(restored)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(restored)
    assert encoded == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("explicit", [False, True], ids=["frozen-omission", "frozen-present"])
@pytest.mark.parametrize("fn,field", [("configure_item_stats", "target"), ("move_straight", "params")])
def test_real_repair_preserves_valid_envelope_presence_and_frozen_siblings(monkeypatch, format_mode, explicit, fn, field):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope
    from test_repair_gameplay_contract import _offline_gameplay_repair
    expected = build_capability_witness(fn)
    if explicit:
        expected = _explicit_calls(expected)
    broken = deepcopy(expected)
    call = next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == fn)
    candidate = deepcopy(call)
    path = "params.damage" if fn == "configure_item_stats" else "target"
    if fn == "configure_item_stats":
        call["params"]["damage"] = -1
        body_id = next(row["id"] for row in broken["runtimeProgram"]["entities"] if row["kind"] == "item_body")
        if explicit:
            candidate.pop("target")
        else:
            candidate["target"] = body_id
    else:
        call["target"] = "missing"
        if explicit:
            candidate.pop("params")
        else:
            candidate["params"] = {}
    before = deepcopy(broken)
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": [path]}]
    incoming = {"note": "fix only actual invalid leaf", "realizationReplacement": broken["realization"], "callsUpsert": [candidate]}
    if explicit:
        # A missing upsert property means no edit; challenge an actual deletion separately.
        incoming["callPropertyKeysDelete"] = [{"callId": call["id"], "key": field}]
    repaired, dossier = _offline_gameplay_repair(monkeypatch, broken, incoming, format_mode)
    assert dossier["repairScope"] == scope
    assert repaired["runtimeProgram"] == expected["runtimeProgram"]
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    assert audit["ok"] and audit["ignoredChanges"], "Valid selector presence changes are audited and ignored"
    repaired.pop("debug")
    assert repaired == expected
    assert compile_runtime_program(repaired) == compile_runtime_program(expected)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert broken == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("explicit", [False, True], ids=["sparse", "explicit"])
def test_real_repair_ignores_hostile_retarget_when_only_damage_is_invalid(monkeypatch, format_mode, explicit):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope
    from test_repair_gameplay_contract import _offline_gameplay_repair
    expected = build_capability_witness("configure_item_stats")
    if explicit:
        expected = _explicit_calls(expected)
    broken = deepcopy(expected)
    call = broken["runtimeProgram"]["calls"][0]
    candidate = deepcopy(call)
    call["params"]["damage"] = -1
    candidate["target"] = "foreign_owner"
    before = deepcopy(broken)
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.damage"]}]
    repaired, _ = _offline_gameplay_repair(monkeypatch, broken,
        {"note": "hostile selector beside valid leaf correction", "realizationReplacement": broken["realization"], "callsUpsert": [candidate]}, format_mode)
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert repaired == expected
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert broken == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_real_repair_corrects_invalid_present_noarg_params_without_retargeting(monkeypatch, format_mode):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope
    from test_repair_gameplay_contract import _offline_gameplay_repair
    expected = _explicit_calls(build_capability_witness("move_straight"))
    broken = deepcopy(expected)
    call = next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "move_straight")
    candidate = deepcopy(call)
    call["params"] = None
    candidate["target"] = "foreign_owner"
    before = deepcopy(broken)
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params"]}]
    repaired, _ = _offline_gameplay_repair(monkeypatch, broken,
        {"note": "explicit empty params correction only", "realizationReplacement": broken["realization"], "callsUpsert": [candidate]}, format_mode)
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    assert audit["ok"] and audit["ignoredChanges"]
    repaired.pop("debug")
    assert repaired == expected
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert broken == before


@pytest.mark.parametrize("fn", [cap.name for cap in visible_capabilities() if cap.target_kinds == ("item_body",)])
def test_source_provenance_rejects_global_item_target_forgery(fn):
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    source = build_capability_witness(fn)
    wire = compile_runtime_program(source)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    forged = deepcopy(source)
    call = next(row for row in forged["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["target"] = "missing"
    before = deepcopy((forged, wire, receipts))
    assert not validate_runtime_program(forged)["ok"]
    wire_only = audit_compiler_receipts(receipts, final_document=wire)
    assert wire_only["ok"] and wire_only["authoredSourceChecked"] is False
    audit = audit_compiler_receipts(receipts, authored_document=forged, final_document=wire)
    assert not audit["ok"], "Unchanged valid wire/receipts must not authenticate a forged source owner"
    assert any(row.get("callId") == call["id"] and row["reason"] ==
               "capability receipt item owner differs from the unique declared body and final item identity"
               for row in audit["violations"]), audit
    assert (forged, wire, receipts) == before


@pytest.mark.parametrize("owner_field,value", [
    pytest.param("target", "missing", id="missing-reference"),
    pytest.param("target", "item", id="no-literal-item-alias"),
    pytest.param("target", "nail", id="declared-projectile"),
    pytest.param("target", "", id="empty-target"),
    pytest.param("target", None, id="null-target"),
    pytest.param("target", True, id="boolean-target"),
    pytest.param("target", 1, id="integer-target"),
    pytest.param("target", [], id="list-target"),
    pytest.param("target", {}, id="object-target"),
    pytest.param("bodies", "ambiguous", id="ambiguous-body"),
    pytest.param("bodies", "absent", id="no-body"),
    pytest.param("bodies", "duplicate-id", id="duplicate-source-identity"),
    pytest.param("body-id", None, id="null-body-identity"),
    pytest.param("body-id", True, id="boolean-body-identity"),
    pytest.param("body-id", 1, id="integer-body-identity"),
    pytest.param("body-id", "", id="empty-body-identity"),
    pytest.param("body-id", "Opaque", id="invalid-body-id-token"),
    pytest.param("itemEntityId", "nail", id="wrong-final-item-owner"),
    pytest.param("itemEntityId", None, id="null-final-item-owner"),
    pytest.param("itemEntityId", True, id="boolean-final-item-owner"),
    pytest.param("itemEntityId", 1, id="integer-final-item-owner"),
    pytest.param("itemEntityId", [], id="list-final-item-owner"),
    pytest.param("itemEntityId", {}, id="object-final-item-owner"),
    pytest.param("itemEntityId", "absent", id="missing-final-item-owner"),
])
def test_item_receipt_owner_requires_exact_declared_and_final_identity(owner_field, value):
    import json
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    source = build_runtime_fixture("workbench_blade")
    program = source["runtimeProgram"]
    body = next(row for row in program["entities"] if row["kind"] == "item_body")
    old_id = body["id"]
    body["id"] = "opaque_body"
    if program["primaryEntityId"] == old_id:
        program["primaryEntityId"] = body["id"]
    for call in program["calls"]:
        if call.get("target") == old_id:
            call["target"] = body["id"]
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    wire_bytes = json.dumps(wire, ensure_ascii=False)
    for positive in (source, _explicit_calls(source)):
        assert json.dumps(compile_runtime_program(positive), ensure_ascii=False) == wire_bytes
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                       authored_document=positive, final_document=wire)["ok"]
    forged = deepcopy(source)
    forged_program = forged["runtimeProgram"]
    call = next(row for row in forged_program["calls"] if row["fn"] == "configure_item_stats")
    if owner_field == "target":
        call["target"] = value
    elif owner_field == "bodies":
        forged_body = next(row for row in forged_program["entities"] if row["kind"] == "item_body")
        if value == "absent":
            forged_program["entities"].remove(forged_body)
        else:
            forged_program["entities"].append({"id": "other_body" if value == "ambiguous" else forged_body["id"],
                                               "kind": "item_body" if value == "ambiguous" else "free_projectile"})
    elif owner_field == "body-id":
        next(row for row in forged_program["entities"] if row["kind"] == "item_body")["id"] = value
        call["target"] = value  # Coherent malformed identities must not authenticate each other.
    else:
        if value == "absent":
            wire["runtimeProgram"].pop("itemEntityId")
        else:
            wire["runtimeProgram"]["itemEntityId"] = value
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    before = json.dumps((forged, wire, receipts), ensure_ascii=False)
    if owner_field != "itemEntityId":
        wire_only = audit_compiler_receipts(receipts, final_document=wire)
        assert wire_only["ok"] and wire_only["authoredSourceChecked"] is False
    audit = audit_compiler_receipts(receipts, authored_document=forged, final_document=wire)
    assert not audit["ok"]
    assert any(row.get("callId") == call["id"] and row["reason"] ==
               "capability receipt item owner differs from the unique declared body and final item identity"
               for row in audit["violations"]), audit
    assert json.dumps((forged, wire, receipts), ensure_ascii=False) == before


@pytest.mark.parametrize("explicit", [False, True])
def test_source_provenance_rejects_equal_value_call_target_swap(explicit):
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    source = build_capability_witness("move_straight")
    program = source["runtimeProgram"]
    original = next(row for row in program["entities"] if row["id"] == "witness_entity")
    program["entities"].append({**deepcopy(original), "id": "other_projectile"})
    binding = deepcopy(program["bindings"][0])
    binding.update(id="other_use", input="alternate_use")
    binding["action"]["targetId"] = "other_projectile"
    program["bindings"].append(binding)
    for call in list(program["calls"]):
        if call.get("target") == "witness_entity":
            program["calls"].append({**deepcopy(call), "id": "other_" + call["id"], "target": "other_projectile"})
    if explicit:
        source = _explicit_calls(source)
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    forged = deepcopy(source)
    for call in forged["runtimeProgram"]["calls"]:
        if call["fn"] == "set_projectile_lifetime":
            call["target"] = "other_projectile" if call["target"] == "witness_entity" else "witness_entity"
    assert validate_runtime_program(forged)["ok"], "Negative reaches provenance with an otherwise valid source"
    audit = audit_compiler_receipts(receipts, authored_document=forged, final_document=wire)
    assert not audit["ok"]
    assert any(row["reason"] == "capability receipt final entity differs from its exact authored target" for row in audit["violations"]), audit


def test_noarg_call_accepts_empty_params_and_exact_omission_without_old_author_admission():
    source = build_runtime_fixture("workbench_blade")
    source["runtimeProgram"]["schema"] = "infini.runtime-program.authoring.v5"
    noarg = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "move_straight")
    noarg.pop("params", None)
    before = deepcopy(source)
    report = validate_runtime_program(source)
    assert report["ok"], report
    wire = compile_runtime_program(source)
    assert wire["runtimeProgram"]["schema"] == "infini.runtime-program.wire.v3"
    assert validate_runtime_wire(wire)["ok"]
    assert source == before
    for version in ("infini.runtime-program.authoring.v4", "infini.runtime-program.authoring.compact.v1"):
        bad = deepcopy(source)
        bad["runtimeProgram"]["schema"] = version
        assert not validate_runtime_program(bad)["ok"]
        from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
        audit = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=bad, final_document=wire)
        assert not audit["ok"]
        assert audit["violations"][0]["reason"] == "source provenance requires the sole current Author grammar"
    explicit = deepcopy(source)
    next(row for row in explicit["runtimeProgram"]["calls"] if row["id"] == noarg["id"])["params"] = {}
    assert validate_runtime_program(explicit)["ok"]
    assert compile_runtime_program(explicit) == wire
    for invalid in (None, [], {"speed": 1}):
        bad = deepcopy(explicit)
        next(row for row in bad["runtimeProgram"]["calls"] if row["id"] == noarg["id"])["params"] = invalid
        report = validate_runtime_program(bad)
        assert not report["ok"]
        assert any(".params" in row["path"] for row in report["errors"])


def test_flat_active_binding_preserves_independent_contact_and_stack_lanes():
    source = build_runtime_fixture("workbench_blade")
    for binding in source["runtimeProgram"]["bindings"]:
        if "usePolicy" in binding:
            binding.update(binding.pop("usePolicy"))
    before = deepcopy(source)
    report = validate_runtime_program(source)
    assert report["ok"], report
    wire = compile_runtime_program(source)
    for binding in source["runtimeProgram"]["bindings"]:
        projected = next(row for row in wire["runtimeProgram"]["bindings"] if row["id"] == binding["id"])
        assert projected["input"] == binding["input"]
        assert projected["usePolicy"]["stackCost"] == binding["stackCost"]
        assert projected["usePolicy"]["contactDamage"] is binding["contactDamage"]
        assert projected["usePolicy"]["action"] == binding["action"]
    assert validate_runtime_wire(wire)["ok"]
    assert source == before
    bad = deepcopy(source)
    binding = bad["runtimeProgram"]["bindings"][0]
    binding["usePolicy"] = {key: binding.pop(key) for key in ("action", "stackCost", "contactDamage")}
    assert not validate_runtime_program(bad)["ok"]
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    assert not audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=bad, final_document=wire)["ok"]


def test_fixed_branches_and_unique_arbitrary_body_references_are_exact():
    from infini_local.qa.capability_witnesses import build_capability_witness
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
    source = build_capability_witness("configure_accessory")
    source["runtimeProgram"]["entities"][0]["id"] = "opaque_body"
    source["runtimeProgram"]["primaryEntityId"] = "opaque_body"
    for call in source["runtimeProgram"]["calls"]:
        if CAPABILITY_REGISTRY[call["fn"]].target_kinds == ("item_body",):
            call.pop("target", None)
    source["runtimeProgram"]["bindings"] = [{"id": "equip", "input": "equipped"}]
    report = validate_runtime_program(source)
    assert report["ok"], report
    wire = compile_runtime_program(source)
    binding = wire["runtimeProgram"]["bindings"][0]
    assert binding["usePolicy"] == {"action": {"kind": "equip_passive", "targetId": "opaque_body"}, "stackCost": 0, "contactDamage": False}
    assert wire["runtimeProgram"]["primaryEntityId"] == "opaque_body"
    explicit = deepcopy(source)
    explicit["runtimeProgram"]["calls"][0]["target"] = "opaque_body"
    assert validate_runtime_program(explicit)["ok"]
    assert compile_runtime_program(explicit) == wire
    for target in ("item", "missing", "", None, 1, True):
        bad = deepcopy(source)
        bad["runtimeProgram"]["calls"][0]["target"] = target
        assert not validate_runtime_program(bad)["ok"]
    explicit_binding = deepcopy(source)
    explicit_binding["runtimeProgram"]["bindings"][0].update(
        action={"kind": "equip_passive", "targetId": "opaque_body"}, stackCost=0, contactDamage=False)
    assert validate_runtime_program(explicit_binding)["ok"]
    projected = compile_runtime_program(explicit_binding)
    assert projected["runtimeProgram"] == wire["runtimeProgram"]
    for foreign, value in (("action", {"kind": "use_item_body"}), ("stackCost", 1), ("contactDamage", True)):
        bad = deepcopy(source)
        bad["runtimeProgram"]["bindings"][0][foreign] = value
        assert not validate_runtime_program(bad)["ok"]


def test_source_receipts_reject_direct_lane_mutation_and_missing_proof():
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    source = build_runtime_fixture("workbench_blade")
    wire = compile_runtime_program(source)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    for key, value in (("input", "alternate_use"), ("stackCost", 1), ("stackCost", True), ("contactDamage", False), ("contactDamage", 1)):
        bad = deepcopy(wire)
        binding = bad["runtimeProgram"]["bindings"][0]
        (binding if key == "input" else binding["usePolicy"])[key] = value
        assert not audit_compiler_receipts(receipts, authored_document=source, final_document=bad)["ok"], key
    for key, value in (("kind", "use_item_body"), ("targetId", "nail")):
        bad = deepcopy(wire)
        bad["runtimeProgram"]["bindings"][0]["usePolicy"]["action"][key] = value
        assert not audit_compiler_receipts(receipts, authored_document=source, final_document=bad)["ok"], key
    bad = deepcopy(wire)
    bad["runtimeProgram"]["primaryEntityId"] = "nail"
    assert not audit_compiler_receipts(receipts, authored_document=source, final_document=bad)["ok"]
    direct = [row for row in receipts if row.get("lowererId") == "author_binding_lanes"]
    assert direct
    assert all(not any("usePolicy" in path for path in row["authoredPaths"]) for row in direct)
    reduced = [row for row in receipts if row not in direct]
    assert not audit_compiler_receipts(reduced, authored_document=source, final_document=wire)["ok"]


def test_current_scoped_repair_preserves_original_bad_rows_and_frozen_lanes():
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch
    source = build_runtime_fixture("workbench_blade")
    binding = source["runtimeProgram"]["bindings"][0]
    binding["stackCost"] = True
    source["runtimeProgram"]["calls"].insert(0, None)
    before = deepcopy(source)
    report = validate_runtime_program(source)
    scope = build_runtime_repair_scope(source, report["errors"])
    filtered, audit = filter_repair_patch_scope(source, {"note": "no-op"}, scope)
    assert not audit["ok"], "a no-op preserves the rejected source rather than completing Repair"
    assert apply_repair_patch(source, filtered) == before
    assert scope["deletable"]["callIndices"] == [0]
    correction = deepcopy(binding)
    correction.update(stackCost=0, contactDamage=False)
    patch = {"note": "exact correction and original-index deletion", "bindingsUpsert": [correction], "callIndicesDelete": [0]}
    filtered, audit = filter_repair_patch_scope(source, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(source, filtered)
    assert repaired["runtimeProgram"]["bindings"][0]["contactDamage"] is True
    assert repaired["runtimeProgram"]["bindings"][0]["stackCost"] == 0
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert source == before


def test_actual_initial_format_and_scoped_repair_builders_share_current_grammar(monkeypatch):
    import json
    from infini_local.pipelines import llm_authoring_pipeline as pipeline
    from infini_local.pipelines import llm_transport as transport
    from test_repair_gameplay_contract import _offline_gameplay_repair
    source = build_runtime_fixture("workbench_blade")
    for mode in ("json_object", "json_schema"):
        monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", mode)
        request, user, _ = pipeline.build_initial_author_request({}, {}, {}, {}, "canonical-offline", model_name="offline")
        card = json.loads(user)["runtimeCapabilityContract"]["shape"] if "shape" in json.loads(user)["runtimeCapabilityContract"] else json.loads(user)["requiredJsonShape"]
        assert "usePolicy" not in json.dumps(card)
        assert "authoring.v5" in json.dumps(card)
        broken = deepcopy(source)
        stats = next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
        stats["params"]["damage"] = True
        correction = deepcopy(stats)
        correction["params"]["damage"] = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")["params"]["damage"]
        patch = {"note": "exact damage correction", "realizationReplacement": broken["realization"], "callsUpsert": [correction]}
        repaired, dossier = _offline_gameplay_repair(monkeypatch, broken, patch, mode)
        assert "usePolicy" not in json.dumps(dossier["requiredJsonShape"])
        assert repaired["runtimeProgram"] == source["runtimeProgram"]
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    content = json.dumps(source)
    requests = []
    def respond(request, **kwargs):
        requests.append(request)
        return {"choices": [{"message": {"content": content}}]}
    monkeypatch.setattr(pipeline, "llm_chat_json", respond)
    prepared, _ = pipeline._repair_malformed_author_json(malformed_raw_text=content[:-1] + ",}",
        parse_error=ValueError("trailing comma"), original_recipe_context=user, model_name="offline")
    assert prepared == source
    assert "usePolicy" not in json.dumps(json.loads(requests[0]["messages"][1]["content"])["requiredJsonShape"])


def test_unresolved_body_is_declaration_repair_not_synthetic_target_authority():
    from infini_local.qa.capability_witnesses import build_capability_witness
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch
    for case in ("missing", "duplicate", "invalid"):
        source = build_capability_witness("configure_accessory")
        body = deepcopy(source["runtimeProgram"]["entities"][0])
        if case == "missing":
            source["runtimeProgram"]["entities"] = []
        elif case == "duplicate":
            source["runtimeProgram"]["entities"].insert(0, {**body, "id": "extra_body"})
        else:
            source["runtimeProgram"]["entities"][0]["id"] = True
        source["runtimeProgram"]["calls"].insert(0, None)
        before = deepcopy(source)
        report = validate_runtime_program(source)
        assert not report["ok"]
        assert not any(row["path"].endswith((".target", ".targetId", ".action.kind")) for row in report["errors"]), report
        scope = build_runtime_repair_scope(source, report["errors"])
        assert scope["fieldPermissions"]["calls"] == []
        assert scope["fieldPermissions"]["bindings"] == []
        no_op, audit = filter_repair_patch_scope(source, {"note": "no-op"}, scope)
        assert not audit["ok"] and apply_repair_patch(source, no_op) == source
        patch = {"note": "explicit declaration", "callIndicesDelete": [0]}
        if case == "duplicate":
            patch["entityIdsDelete"] = ["extra_body"]
        else:
            patch["entitiesUpsert"] = [body]
            if case == "invalid":
                patch["entityIndicesDelete"] = [0]
        filtered, audit = filter_repair_patch_scope(source, patch, scope)
        assert audit["ok"], audit
        repaired = apply_repair_patch(source, filtered)
        assert validate_runtime_program(repaired)["ok"]
        assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
        assert source == before


def test_semantic_paths_keep_original_indices_past_malformed_rows():
    source = build_runtime_fixture("workbench_blade")
    source["runtimeProgram"]["calls"].insert(0, None)
    index = next(i for i, row in enumerate(source["runtimeProgram"]["calls"]) if isinstance(row, dict) and row["fn"] == "set_projectile_damage")
    source["runtimeProgram"]["calls"][index]["target"] = "missing"
    report = validate_runtime_program(source)
    assert any(row["code"] == "missing_entity_reference" and row["path"] == f"$.runtimeProgram.calls[{index}].target" for row in report["errors"]), report


def test_derived_role_receipts_reference_only_real_source_dependencies():
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    source = build_runtime_fixture("fishing_platform_tool")
    wire = compile_runtime_program(source)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    roles = [row for row in receipts if row.get("lowererId") == "primary_entity_to_binding_role"]
    assert roles
    assert all(not any(path.endswith(".action.targetId") for path in row["authoredPaths"]) for row in roles)
    assert all(any(path.endswith(".kind") and ".entities[" in path for path in row["authoredPaths"]) for row in roles)
    forged = deepcopy(receipts)
    next(row for row in forged if row.get("lowererId") == "primary_entity_to_binding_role")["authoredPaths"][-1] = "runtimeProgram.entities[99].id"
    assert not audit_compiler_receipts(forged, authored_document=source, final_document=wire)["ok"]


def test_current_placement_association_has_only_literal_source_paths():
    import re
    from test_placed_body_capability import placed
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    source = placed()
    wire = compile_runtime_program(source)
    association = next(row for row in wire["runtimeContract"]["finalWireReceipts"]
                       if row.get("fn") == "present_placed_item_sprite" and row.get("status") == "technical_projection")
    def read(path):
        value = source
        for key, index in re.findall(r"([A-Za-z][A-Za-z0-9_]*)|\[(\d+)\]", path):
            value = value[int(index)] if index else value[key]
        return value
    assert all(read(path) is not None for path in association["authoredPaths"])
    assert any(path.endswith(".id") and ".entities[" in path for path in association["authoredPaths"])
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)["ok"]


def test_wire_only_placement_reader_keeps_explicit_nested_policy_contract():
    source = build_runtime_fixture("fishing_platform_tool")
    wire = compile_runtime_program(source)
    wire.pop("runtimeContract")
    binding = next(row for row in wire["runtimeProgram"]["bindings"] if row["usePolicy"]["action"]["kind"] == "place_item")
    binding["input"] = "primary_use"
    assert any(row["code"] == "dual_use_placeable_input_contract" for row in validate_runtime_wire(wire)["errors"])


def test_source_native_repair_can_create_implied_item_call_without_authored_target():
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch
    source = build_runtime_fixture("workbench_blade")
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "configure_item_use")
    source["runtimeProgram"]["calls"].remove(call)
    scope = build_runtime_repair_scope(source, validate_runtime_program(source)["errors"])
    filtered, audit = filter_repair_patch_scope(source, {"note": "literal implied call", "callsUpsert": [call]}, scope)
    assert audit["ok"], audit
    assert "target" not in filtered["callsUpsert"][0]
    repaired = apply_repair_patch(source, filtered)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


def test_real_author_card_uses_one_explicit_call_envelope(monkeypatch):
    import json
    from infini_local.core.runtime_authoring.capability_registry import capability_provider_union
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    request, _, _ = build_initial_author_request({}, {}, {}, {}, "current-call-grammar", model_name="offline")
    packet = json.loads(request["messages"][1]["content"])
    calls = packet["requiredJsonShape"]["runtimeProgram"]["calls"]
    assert {frozenset(row) for row in calls} == {
        frozenset(variant["properties"]) for variant in capability_provider_union()
    } == {frozenset(("id", "fn", "target", "params"))}
    guide = packet["runtimeCapabilityContract"]["catalog"]["fieldGuide"]
    assert "one explicit id/fn/target/params envelope" in guide["rowShapes"]
    assert "zero-argument calls use params={}" in guide["rowShapes"]
    assert "Exact existing omissions remain valid in the same grammar" in guide["rowShapes"]
    assert "not a literal item alias" in guide["rowShapes"]
    assert "usePolicy" not in guide["bindingTarget"] and "omit" in guide["rowShapes"]


def test_malformed_active_input_repairs_source_leaf_and_freezes_group_and_lanes():
    from infini_local.qa.capability_witnesses import build_capability_witness
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch
    for value in ({}, [], None, "unknown"):
        source = build_capability_witness("restore_resources_on_use")
        call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "restore_resources_on_use")
        call["params"]["effectGroupId"] = "exact_group"
        binding = source["runtimeProgram"]["bindings"][0]
        binding["action"]["effectGroupId"] = "exact_group"
        binding["input"] = value
        before = deepcopy(source)
        report = validate_runtime_program(source)
        scope = build_runtime_repair_scope(source, report["errors"])
        assert scope["fieldPermissions"]["bindings"] == [{"id": binding["id"], "paths": ["input"]}], report
        correction = deepcopy(binding)
        correction.update(input="primary_use", stackCost=1, contactDamage=True)
        correction["action"]["effectGroupId"] = "foreign_group"
        filtered, audit = filter_repair_patch_scope(source, {"note": "literal input", "bindingsUpsert": [correction]}, scope)
        assert audit["ok"], audit
        repaired = apply_repair_patch(source, filtered)
        expected = deepcopy(source)
        expected["runtimeProgram"]["bindings"][0]["input"] = "primary_use"
        assert repaired == expected
        assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
        assert source == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("value", ["unknown", {}, None])
def test_omission_only_passive_selector_repair_has_only_input_authority(monkeypatch, format_mode, value):
    from infini_local.qa.capability_witnesses import build_capability_witness
    from infini_local.core.runtime_authoring import build_runtime_repair_scope
    from test_repair_gameplay_contract import _offline_gameplay_repair
    source = build_capability_witness("configure_accessory")
    from test_item_effect_groups import _groups
    groups = _groups()
    groups["runtimeProgram"]["bindings"][0]["id"] = "group_primary"
    groups["runtimeProgram"]["calls"][2]["id"] = "group_effect"
    source["runtimeProgram"]["calls"].extend(deepcopy(row) for row in groups["runtimeProgram"]["calls"] if row["fn"] == "restore_resources_on_use")
    source["runtimeProgram"]["bindings"].extend(deepcopy(groups["runtimeProgram"]["bindings"]))
    binding = source["runtimeProgram"]["bindings"][0]
    assert set(binding) == {"id", "input"}
    binding["input"] = value
    before = deepcopy(source)
    report = validate_runtime_program(source)
    scope = build_runtime_repair_scope(source, report["errors"])
    assert scope["fieldPermissions"]["bindings"] == [{"id": binding["id"], "paths": ["input"]}]
    fixed = {"id": binding["id"], "input": "equipped"}
    hostile = deepcopy(source["runtimeProgram"]["bindings"][1])
    hostile["action"]["effectGroupId"] = "second"
    repaired, _ = _offline_gameplay_repair(monkeypatch, source,
        {"note": "explicit passive selector", "realizationReplacement": source["realization"], "bindingsUpsert": [fixed, hostile]}, format_mode)
    assert repaired["runtimeProgram"]["bindings"] == [fixed, *source["runtimeProgram"]["bindings"][1:]]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    assert repaired["runtimeProgram"]["calls"] == source["runtimeProgram"]["calls"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert source == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("value", [{}, None, ""])
def test_noop_repair_preserves_malformed_whole_binding_container(monkeypatch, format_mode, value):
    from infini_local.core.runtime_authoring import apply_repair_patch
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.qa.capability_witnesses import build_capability_witness
    from test_repair_gameplay_contract import _offline_gameplay_repair
    source = build_capability_witness("configure_accessory")
    source["runtimeProgram"]["bindings"] = value
    before = deepcopy(source)
    assert apply_repair_patch(source, {"note": "no-op"}) == source
    with pytest.raises(PlannerUnavailable):
        _offline_gameplay_repair(monkeypatch, source,
            {"note": "no-op", "realizationReplacement": source["realization"]}, format_mode)
    assert source == before
