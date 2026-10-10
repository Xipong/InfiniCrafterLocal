"""Original compact source -> canonical graph -> wire, and frozen ID Repair."""

from copy import deepcopy
import json

import pytest

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, compile_runtime_program, validate_runtime_wire
from infini_local.core.runtime_authoring.compact_api import (
    apply_compact_repair, build_compact_repair_scope, compact_repair_schema,
    compile_compact_author, validate_compact_author,
)
from infini_local.core.runtime_authoring.compact_notation import (
    COMPACT_AUTHOR_SCHEMA, CompactAuthorError, audit_compact_source,
    compact_author_item_schema, encode_compact_author, project_compact_author,
)
from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
from infini_local.pipelines import compact_author_pipeline as transport
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import NON_ARCHETYPAL_FIXTURES, build_runtime_fixture
from test_codex_subscription_contract import _encode_nullable_fixture


def _checks(doc):
    return doc["realization"]["selfEvaluation"]["planVsProgram"]["actionChecks"]


def _encode_fixture(doc):
    # Fixture construction explicitly pairs report row N with concept row N.
    # This helper is test-only; production callers always supply their indices.
    return encode_compact_author(doc, planned_action_indices=list(range(len(_checks(doc)))))


def _call(doc, fn):
    return next(call for group in doc["runtimeProgram"]["callGroups"] for call in group["calls"] if call["fn"] == fn)


def _wire(doc):
    return {key: doc[key] for key in ("runtimeProgram", "gameplay", "accessory", "armor")}


@pytest.mark.parametrize("name", NON_ARCHETYPAL_FIXTURES)
def test_control_corpus_exact_source_graph_wire_and_receipt_roundtrip(name):
    original = build_runtime_fixture(name)
    compact = _encode_fixture(original)
    frozen = deepcopy(compact)
    projection = project_compact_author(compact)
    assert projection.canonical == original
    assert not strict_schema_errors(compact, compact_author_item_schema())
    compiled = compile_compact_author(compact)
    reference = compile_runtime_program(original)
    assert compact == frozen
    assert _wire(compiled) == _wire(reference)
    assert compiled["runtimeContract"]["finalWireReceipts"] == reference["runtimeContract"]["finalWireReceipts"]
    assert compiled["runtimeContract"]["compactAuthorSource"]["document"] == compact
    assert audit_compact_source(compiled, authored_document=compact)["ok"]
    assert validate_runtime_wire(compiled)["ok"]


@pytest.mark.parametrize("fn", [name for name, cap in CAPABILITY_REGISTRY.items() if cap.prompt_visible and cap.decision == "expose"])
def test_every_public_capability_has_exact_compact_projection(fn):
    original = build_capability_witness(fn)
    compact = _encode_fixture(original)
    assert project_compact_author(compact).canonical == original
    assert _wire(compile_compact_author(compact)) == _wire(compile_runtime_program(original))


def test_consecutive_target_groups_preserve_interleaved_call_order_and_ids():
    original = build_runtime_fixture("workbench_blade")
    calls = original["runtimeProgram"]["calls"]
    item = calls.pop(1)
    calls.insert(4, item)
    compact = _encode_fixture(original)
    groups = compact["runtimeProgram"]["callGroups"]
    targets = [group.get("target") for group in groups]
    assert any(target is not None and targets.count(target) > 1 for target in targets)
    assert [call["id"] for group in groups for call in group["calls"]] == [call["id"] for call in calls]
    assert project_compact_author(compact).canonical == original
    assert _wire(compile_compact_author(compact)) == _wire(compile_runtime_program(original))


@pytest.mark.parametrize("mutation", ["missing_body", "two_bodies", "duplicate_entity_id", "duplicate_call_id", "duplicate_binding_id", "unknown_target", "unknown_group_field", "call_target", "noarg_params", "unknown_root"])
def test_ambiguous_or_unknown_source_structure_fails_closed(mutation):
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    program = compact["runtimeProgram"]
    if mutation == "missing_body":
        program["entities"] = [row for row in program["entities"] if row["kind"] != "item_body"]
    elif mutation == "two_bodies":
        program["entities"].append({"id": "second_item", "kind": "item_body"})
    elif mutation == "duplicate_entity_id":
        program["entities"][-1]["id"] = program["entities"][0]["id"]
    elif mutation == "duplicate_call_id":
        group = program["callGroups"][0]
        group["calls"][1]["id"] = group["calls"][0]["id"]
    elif mutation == "duplicate_binding_id":
        program["bindings"].append(deepcopy(program["bindings"][0]))
    elif mutation == "unknown_target":
        next(row for row in program["callGroups"] if "target" in row)["target"] = "missing_entity"
    elif mutation == "unknown_group_field":
        program["callGroups"][0]["sharedParams"] = {}
    elif mutation == "call_target":
        program["callGroups"][0]["calls"][0]["target"] = "item"
    elif mutation == "noarg_params":
        _call(compact, "move_straight")["params"] = {}
    elif mutation == "unknown_root":
        compact["invented"] = "extra"
    report = validate_compact_author(compact)
    assert not report["ok"], report
    with pytest.raises(CompactAuthorError):
        compile_compact_author(compact)


@pytest.mark.parametrize("field,value", [("stackCost", 0), ("contactDamage", False), ("action", {"kind": "apply_equipped_effects"}), ("usePolicy", {})])
def test_equipped_variant_constants_are_forbidden_even_if_correct(field, value):
    compact = _encode_fixture(build_runtime_fixture("equipment_tool_combat"))
    binding = next(row for row in compact["runtimeProgram"]["bindings"] if row["input"] == "equipped")
    binding[field] = value
    assert not validate_compact_author(compact)["ok"]
    with pytest.raises(CompactAuthorError):
        build_compact_repair_scope(compact)


def test_active_contact_and_stack_choices_are_not_removed():
    original = build_runtime_fixture("shield_and_disc")
    compact = _encode_fixture(original)
    for canonical, source in zip(original["runtimeProgram"]["bindings"], compact["runtimeProgram"]["bindings"]):
        if source["input"] in {"primary_use", "alternate_use"}:
            assert source["stackCost"] == canonical["usePolicy"]["stackCost"]
            assert source["contactDamage"] is canonical["usePolicy"]["contactDamage"]
    assert project_compact_author(compact).canonical == original


def test_planned_index_preserves_duplicate_text_row_identity():
    original = build_runtime_fixture("workbench_blade")
    original["concept"]["plannedPlayerActions"].append(deepcopy(original["concept"]["plannedPlayerActions"][0]))
    compact = encode_compact_author(original, planned_action_indices=[1])
    compiled = compile_compact_author(compact)
    origin = compiled["runtimeContract"]["compactAuthorSource"]["sourceMap"]["realization.selfEvaluation.planVsProgram.actionChecks[0].plannedIntent"]
    assert origin["sourcePaths"][1] == "concept.plannedPlayerActions[1].intent"
    assert _checks(compact)[0]["plannedActionIndex"] == 1
    assert project_compact_author(compact).canonical == original


@pytest.mark.parametrize("value", [None, -1, 1, 7, True, "0"])
def test_report_invalid_reference_is_not_inferred_from_text(value):
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    _checks(compact)[0]["plannedActionIndex"] = value
    assert not validate_compact_author(compact)["ok"]


def test_added_action_requires_an_explicit_null_and_is_reversible():
    original = build_runtime_fixture("workbench_blade")
    _checks(original)[0].update(plannedIntent="no corresponding initial action", result="added")
    compact = encode_compact_author(original, planned_action_indices=[None])
    assert project_compact_author(compact).canonical == original
    del _checks(compact)[0]["plannedActionIndex"]
    with pytest.raises(CompactAuthorError):
        project_compact_author(compact, check_shape=False)


@pytest.mark.parametrize("mutation", ["raw_source", "source_map", "source_receipt", "canonical_receipt", "wire", "concept", "realization", "name", "missing_chain", "missing_source"])
def test_original_source_and_both_receipt_layers_are_checked(mutation):
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    compiled = compile_compact_author(compact)
    contract = compiled["runtimeContract"]
    if mutation == "raw_source":
        _call(contract["compactAuthorSource"]["document"], "configure_item_stats")["params"]["damage"] += 1
    elif mutation == "source_map":
        contract["compactAuthorSource"]["sourceMap"]["runtimeProgram.calls[0].target"]["sourcePaths"] = ["runtimeProgram.callGroups[0].target"]
    elif mutation == "source_receipt":
        contract["compactSourceReceipts"][0]["authoredPaths"] = ["invented"]
    elif mutation == "canonical_receipt":
        contract["finalWireReceipts"][0]["value"] = "invented"
    elif mutation == "wire":
        compiled["gameplay"]["damage"] += 1
    elif mutation == "concept":
        compiled["concept"]["coreMechanic"] += " changed"
    elif mutation == "realization":
        compiled["realization"]["description"] += " changed"
    elif mutation == "name":
        compiled["name"] += " changed"
    elif mutation == "missing_chain":
        del contract["compactSourceReceipts"]
    elif mutation == "missing_source":
        del contract["compactAuthorSource"]
    assert not audit_compact_source(compiled, authored_document=compact)["ok"]
    assert not validate_runtime_wire(compiled)["ok"]


def test_scope_errors_use_original_group_paths_and_repair_freezes_neighbors():
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    # Deliberately retain two consecutive item groups. Repair cannot coalesce them.
    group = compact["runtimeProgram"]["callGroups"][0]
    compact["runtimeProgram"]["callGroups"][0:1] = [{"calls": group["calls"][:1]}, {"calls": group["calls"][1:]}]
    use = _call(compact, "configure_item_use")
    old_style = use["params"].pop("useStyle")
    before = deepcopy(compact)
    scope = build_compact_repair_scope(compact)
    assert any("callGroups[1].calls[0].params.useStyle" in row["path"] for row in scope["errors"]), scope["errors"]
    fixed = deepcopy(use)
    fixed["params"].update(useStyle=old_style, autoReuse=not use["params"]["autoReuse"])
    repaired, audit = apply_compact_repair(compact, {"callsUpsert": [fixed], "note": "restore only the missing useStyle"}, scope)
    expected = deepcopy(before)
    _call(expected, "configure_item_use")["params"]["useStyle"] = old_style
    assert audit["ok"], audit
    assert audit["ignoredChanges"]
    assert repaired == expected
    assert compact == before
    compile_compact_author(repaired)


def test_repair_report_reference_is_explicit_and_concept_stays_frozen():
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    _checks(compact)[0]["plannedActionIndex"] = 7
    scope = build_compact_repair_scope(compact)
    replacement = deepcopy(compact["realization"])
    replacement["selfEvaluation"]["planVsProgram"]["actionChecks"][0]["plannedActionIndex"] = 0
    repaired, audit = apply_compact_repair(compact, {"realizationReplacement": replacement, "note": "explicit plan row 0"}, scope)
    assert audit["ok"], audit
    assert repaired["concept"] == compact["concept"]
    assert repaired["runtimeProgram"] == compact["runtimeProgram"]
    assert _checks(repaired)[0]["plannedActionIndex"] == 0


def test_target_repair_splits_group_without_retargeting_a_valid_sibling():
    original = build_runtime_fixture("workbench_blade")
    calls = original["runtimeProgram"]["calls"]
    event = next(row for row in calls if row["fn"] == "spawn_entity_on_event")
    life = next(row for row in calls if row["fn"] == "set_projectile_lifetime")
    calls.remove(event)
    calls.remove(life)
    event["target"] = "item"
    event["params"]["event"] = "on_use"
    compact = _encode_fixture(original)
    group = {"target": "item", "calls": [{key: deepcopy(value) for key, value in row.items() if key != "target"} for row in (event, life)]}
    compact["runtimeProgram"]["callGroups"].append(group)
    assert not validate_compact_author(compact)["ok"]
    before = deepcopy(compact)
    repaired, audit = apply_compact_repair(compact, {"callsUpsert": [deepcopy(life)], "note": "only the invalid lifetime target"})
    assert audit["ok"], audit
    assert compact == before
    assert repaired["runtimeProgram"]["callGroups"][-2] == {"target": "item", "calls": [group["calls"][0]]}
    assert repaired["runtimeProgram"]["callGroups"][-1] == {"target": life["target"], "calls": [group["calls"][1]]}
    assert [row["id"] for g in compact["runtimeProgram"]["callGroups"] for row in g["calls"]] == [row["id"] for g in repaired["runtimeProgram"]["callGroups"] for row in g["calls"]]
    compile_compact_author(repaired)


@pytest.mark.parametrize("mutation", ["stale_source", "permissions", "source_map"])
def test_repair_scope_is_bound_to_the_exact_source_and_permissions(mutation):
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    _call(compact, "configure_item_use")["params"].pop("useStyle")
    scope = build_compact_repair_scope(compact)
    if mutation == "stale_source":
        compact["name"] += " changed"
    elif mutation == "permissions":
        scope["canonicalScope"]["mutable"] = {}
    else:
        scope["sourceMap"] = {}
    with pytest.raises(CompactAuthorError):
        apply_compact_repair(compact, {"note": "no permission expansion"}, scope)


def test_grouping_does_not_multiply_the_total_call_limit():
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    call = _call(compact, "configure_item_stats")
    rows = [{**deepcopy(call), "id": f"call_{index}"} for index in range(49)]
    compact["runtimeProgram"]["callGroups"] = [{"calls": rows[:25]}, {"calls": rows[25:]}]
    report = validate_compact_author(compact)
    assert not report["ok"] and any(row["code"] == "total_call_limit" for row in report["errors"]), report


@pytest.mark.parametrize("name", NON_ARCHETYPAL_FIXTURES)
def test_strict_provider_transport_roundtrip_is_exact(name, monkeypatch):
    monkeypatch.setenv("INFINI_LLM_RESPONSE_FORMAT", "json_schema")
    compact = _encode_fixture(build_runtime_fixture(name))
    schema = compact_author_item_schema()
    encoded = _encode_nullable_fixture(compact, schema)
    request, user, _ = transport.build_compact_author_request({}, {}, {}, {}, "fixture", model_name="test-model")
    assert not strict_schema_errors(encoded, request["response_format"]["json_schema"]["schema"])
    assert transport.accept_compact_author_response(encoded, response_format=request["response_format"]) == compact
    payload = json.loads(user)
    assert payload["requiredJsonShape"]["runtimeProgram"]["schema"] == COMPACT_AUTHOR_SCHEMA
    assert "usePolicy" not in json.dumps(payload["requiredJsonShape"])
    assert "bindings[].usePolicy" not in user


def test_transport_decoder_respects_downgrade_and_does_not_strip_arbitrary_null(monkeypatch):
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    _call(compact, "configure_item_stats")["params"].pop("manaCost")
    encoded = _encode_nullable_fixture(compact, compact_author_item_schema())
    monkeypatch.setattr(transport, "llm_chat_json", lambda *a, **k: {
        "choices": [{"message": {"content": json.dumps(encoded)}}], "_debug": {"strictSchemaDowngraded": True},
    })
    accepted = transport.request_compact_author({}, {}, {}, {}, "fixture", model_name="test-model")
    assert _call(accepted, "configure_item_stats")["params"]["manaCost"] is None
    assert not validate_compact_author(accepted)["ok"]


def test_transport_requires_explicit_version_and_known_root():
    canonical = build_runtime_fixture("workbench_blade")
    with pytest.raises(PlannerUnavailable):
        transport.accept_compact_author_response(canonical)
    compact = _encode_fixture(canonical)
    compact["unknown"] = None
    with pytest.raises(PlannerUnavailable):
        transport.accept_compact_author_response(compact)


def test_compact_patch_provider_projection_and_frozen_merge(monkeypatch):
    monkeypatch.setenv("INFINI_LLM_RESPONSE_FORMAT", "json_schema")
    compact = _encode_fixture(build_runtime_fixture("workbench_blade"))
    fixed = deepcopy(_call(compact, "configure_item_use"))
    _call(compact, "configure_item_use")["params"].pop("useStyle")
    patch = {"callsUpsert": [fixed], "note": "restore explicit style"}
    encoded = _encode_nullable_fixture(patch, compact_repair_schema())
    request, scope = transport.build_compact_repair_request(compact, model_name="test-model")
    assert not strict_schema_errors(encoded, request["response_format"]["json_schema"]["schema"])
    repaired, audit = transport.accept_compact_repair_response(compact, encoded, scope, response_format=request["response_format"])
    assert audit["ok"] and validate_compact_author(repaired)["ok"]
