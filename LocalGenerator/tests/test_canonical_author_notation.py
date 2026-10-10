"""Current Author notation: one source admission/compiler/Repair boundary."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import (
    compile_runtime_program, validate_runtime_program, validate_runtime_wire,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def test_current_noarg_call_has_no_params_property_and_no_old_author_admission():
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
    bad = deepcopy(source)
    next(row for row in bad["runtimeProgram"]["calls"] if row["id"] == noarg["id"])["params"] = {}
    report = validate_runtime_program(bad)
    assert not report["ok"]
    assert any(row["path"].endswith(".params") for row in report["errors"])


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
    for foreign in ("target", "params"):
        bad = deepcopy(source)
        call = bad["runtimeProgram"]["calls"][0]
        if foreign == "target":
            call["target"] = "opaque_body"
        else:
            continue
        assert not validate_runtime_program(bad)["ok"]
    for foreign, value in (("action", {"kind": "equip_passive"}), ("stackCost", 0), ("contactDamage", False)):
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


def test_real_author_card_explains_forbidden_implied_call_fields(monkeypatch):
    import json
    from infini_local.core.runtime_authoring.capability_registry import capability_provider_union
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    request, _, _ = build_initial_author_request({}, {}, {}, {}, "current-call-grammar", model_name="offline")
    packet = json.loads(request["messages"][1]["content"])
    calls = packet["requiredJsonShape"]["runtimeProgram"]["calls"]
    assert {frozenset(row) for row in calls} == {
        frozenset(variant["properties"]) for variant in capability_provider_union()
    } == {frozenset(keys) for keys in (("id", "fn", "params"), ("id", "fn", "target", "params"), ("id", "fn", "target"))}
    guide = packet["runtimeCapabilityContract"]["catalog"]["fieldGuide"]
    assert "Item-body-only calls omit target" in guide["rowShapes"]
    assert "zero-argument calls omit params" in guide["rowShapes"]
    assert "usePolicy" not in guide["bindingTarget"] and "omit" in guide["bindingTarget"]


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
