"""Opt-in live concurrency is independent of per-activation spawn count."""

import copy
import hashlib
import json

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, ENTITY_KIND_REGISTRY, PROJECTILE_ENTITY_KINDS,
    apply_repair_patch, audit_compiler_receipts, build_runtime_repair_scope,
    capability_provider_union, compile_runtime_program, filter_repair_patch_scope,
    validate_runtime_program, validate_runtime_wire,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.capability_library_audit import _runtime_param_bound_rows
from pathlib import Path
from infini_local.pipelines import llm_authoring_pipeline as gameplay
from test_low_level_three_stage_pipeline import wire_transport


CAPABILITY = "set_projectile_concurrency"


def _with_concurrency(value=1):
    document = build_runtime_fixture("returning_potion")
    document["runtimeProgram"]["calls"].append({
        "id": "tonic_concurrency", "fn": CAPABILITY, "target": "tonic_flask",
        "params": {"maxActive": value},
    })
    return document


def test_explicit_concurrency_projects_only_exact_spawn_leaf_with_receipt():
    old = compile_runtime_program(build_runtime_fixture("returning_potion"))
    document = _with_concurrency()
    report = validate_runtime_program(document)
    assert report["ok"], report["errors"]
    compiled = compile_runtime_program(document)
    expected = copy.deepcopy(old["runtimeProgram"])
    entity_index = next(i for i, row in enumerate(expected["entities"]) if row["id"] == "tonic_flask")
    expected["entities"][entity_index]["spawn"]["maxActive"] = 1
    assert compiled["runtimeProgram"] == expected
    receipts = [row for row in compiled["runtimeContract"]["finalWireReceipts"] if row.get("fn") == CAPABILITY]
    assert receipts == [{
        "callId": "tonic_concurrency", "fn": CAPABILITY,
        "authoredPath": f"runtimeProgram.calls[{len(document['runtimeProgram']['calls']) - 1}].params.maxActive",
        "finalPath": f"runtimeProgram.entities[{entity_index}].spawn.maxActive",
        "value": 1, "status": "delivered",
    }]
    assert compiled["runtimeContract"]["technicalLoweringAudit"]["ok"]
    wire_report = validate_runtime_wire(compiled)
    assert wire_report["ok"], wire_report["errors"]


@pytest.mark.parametrize("value", [None, False, True, 0, 97, 1.0, "1", [], {}])
def test_present_malformed_wire_concurrency_refused_without_author_receipts(value):
    compiled = compile_runtime_program(build_runtime_fixture("returning_potion"))
    compiled.pop("runtimeContract")  # Saved/delivery wire has no Author provenance.
    entity_index = next(i for i, row in enumerate(compiled["runtimeProgram"]["entities"]) if row["id"] == "tonic_flask")
    compiled["runtimeProgram"]["entities"][entity_index]["spawn"]["maxActive"] = value
    before = copy.deepcopy(compiled)
    report = validate_runtime_wire(compiled)
    assert not report["ok"], report
    assert any(row["path"] == f"$.runtimeProgram.entities[{entity_index}].spawn.maxActive" for row in report["errors"])
    assert compiled == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_registry_concurrency_choice_reaches_actual_model_packet(monkeypatch, format_mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", format_mode)
    parent = {"id": "literal", "name": "Literal object", "damage": 7, "useTime": 20}
    request, content, _ = build_initial_author_request(parent, parent, parent, parent, "concurrency", model_name="test-model")
    assert request["messages"][1]["content"] == content
    cards = json.loads(content)["runtimeCapabilityContract"]["catalog"]["capabilities"]
    card = next(row for row in cards if row["fn"] == CAPABILITY)
    assert card == CAPABILITY_REGISTRY[CAPABILITY].author_prompt_card()
    assert set(card["targets"]) == PROJECTILE_ENTITY_KINDS
    assert card["params"]["maxActive"]["type"] == "integer"
    assert (card["params"]["maxActive"]["min"], card["params"]["maxActive"]["max"]) == (1, 96)
    assert "default" not in card["params"]["maxActive"]
    assert "neutral" not in card["params"]["maxActive"]
    assert all(term in card["does"] for term in (
        "opt-in", "owner", "generated item ID", "entity ID", "all producers",
        "root", "child", "binding", "input", "pending scheduler entries",
        "effective batch", "all-or-nothing", "no clipping", "absence",
        "1", "returned physical copy", "larger", "count", "per activation", "separate",
        "different inventory copies", "alternate binding", "share the cap",
        "owner-attached active-use singleton", "hold maintains one", "does not override",
        "maxActive>1",
    ))
    spawn = next(row for row in cards if row["fn"] == "configure_spawn")
    assert CAPABILITY in spawn["params"]["count"]["meaning"]


def test_spawn_alias_keeps_historical_runtime_values_and_concurrency_absence():
    document = build_runtime_fixture("returning_potion")
    before = copy.deepcopy(document)
    compiled = compile_runtime_program(document)
    assert document == before
    historical = copy.deepcopy(compiled["runtimeProgram"])
    for entity in historical["entities"]:
        if "spawn" in entity:
            # Fresh `position.at` now writes these two old zero DTO defaults.
            # The captured hash remains unchanged; compare every other byte.
            assert entity["spawn"].pop("overTarget") == {"heightTiles": 0, "delayTicks": 0}
    fingerprint = hashlib.sha256(json.dumps(historical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # Captured from the accepted old fixture before concurrency implementation.
    assert fingerprint == "beccfa0cf7d8d67c54a27b7f28017d83b1c394277409bcbc662a878766877d04"
    assert all("maxActive" not in row.get("spawn", {}) for row in compiled["runtimeProgram"]["entities"])
    assert not any(row.get("fn") == CAPABILITY for row in compiled["runtimeContract"]["finalWireReceipts"])
    compiled.pop("runtimeContract")
    assert validate_runtime_wire(compiled)["ok"]
    assert all(CAPABILITY not in kind.required_components for kind in ENTITY_KIND_REGISTRY.values())
    assert "maxActive" not in CAPABILITY_REGISTRY["configure_spawn"].params


@pytest.mark.parametrize("value", [None, False, True, 0, 97, 1.0, "1", [], {}])
def test_present_malformed_author_concurrency_refused_at_exact_leaf(value):
    document = _with_concurrency(value)
    before = copy.deepcopy(document)
    report = validate_runtime_program(document)
    assert not report["ok"]
    assert any(row["path"].endswith(".params.maxActive") for row in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    assert document == before


def test_schema_registry_has_required_positive_param_but_optional_capability():
    cap = CAPABILITY_REGISTRY[CAPABILITY]
    variant = next(row for row in capability_provider_union() if row["properties"]["fn"]["const"] == CAPABILITY)
    params = variant["properties"]["params"]
    assert params["required"] == ["maxActive"]
    assert params["properties"]["maxActive"] == cap.params["maxActive"].schema()
    assert cap.params["maxActive"].default is None
    assert cap.params["maxActive"].neutral is None
    assert cap.component_slot == "spawn"
    assert cap.multiplicity == "single_per_target"
    assert not cap.exclusive_group
    assert cap.final_wire_paths == ("runtimeProgram.entities[].spawn.maxActive",)


@pytest.mark.parametrize("value", range(1, 97))
def test_entire_positive_domain_is_exact_not_clipped_and_count_is_independent(value):
    document = _with_concurrency(value)
    spawn = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "configure_spawn")
    spawn["params"]["count"] = 3  # Even count > cap is an explicit, potentially refused batch, not a rewrite.
    document["runtimeProgram"]["calls"].insert(0, document["runtimeProgram"]["calls"].pop())
    compiled = compile_runtime_program(document)
    projectile = next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == "tonic_flask")
    assert projectile["spawn"]["maxActive"] == value
    assert projectile["spawn"]["count"] == 3
    assert validate_runtime_wire(compiled)["ok"]
    compiled.pop("runtimeContract")
    assert validate_runtime_wire(compiled)["ok"]


@pytest.mark.parametrize("kind", sorted(PROJECTILE_ENTITY_KINDS))
def test_same_optional_capability_compiles_for_every_projectile_kind(kind):
    if kind == "child_projectile":
        document = build_runtime_fixture("workbench_blade")
        target = "nail"
    else:
        document = build_runtime_fixture("returning_potion")
        target = "tonic_flask"
        next(row for row in document["runtimeProgram"]["entities"] if row["id"] == target)["kind"] = kind
    document["runtimeProgram"]["calls"].append({"id": "kind_concurrency", "fn": CAPABILITY, "target": target, "params": {"maxActive": 2}})
    report = validate_runtime_program(document)
    assert report["ok"], report["errors"]
    compiled = compile_runtime_program(document)
    assert next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == target)["spawn"]["maxActive"] == 2
    assert validate_runtime_wire(compiled)["ok"]


def test_duplicate_writer_refused_while_other_entity_cap_remains_independent():
    document = _with_concurrency(3)
    duplicate = copy.deepcopy(document["runtimeProgram"]["calls"][-1])
    duplicate["id"] = "second_concurrency"
    document["runtimeProgram"]["calls"].append(duplicate)
    report = validate_runtime_program(document)
    assert any(row["code"] == "duplicate_single_component" for row in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    document = build_runtime_fixture("shield_and_disc")
    for target, value in (("shield_body", 1), ("shield_disc", 6)):
        document["runtimeProgram"]["calls"].append({"id": target + "_cap", "fn": CAPABILITY, "target": target, "params": {"maxActive": value}})
    compiled = compile_runtime_program(document)
    assert {row["id"]: row["spawn"]["maxActive"] for row in compiled["runtimeProgram"]["entities"] if "spawn" in row} == {"shield_body": 1, "shield_disc": 6}


def test_concurrency_rejects_item_target_and_missing_value_without_neutral_fill():
    document = _with_concurrency()
    document["runtimeProgram"]["calls"][-1]["target"] = "item"
    assert any(row["code"] == "wrong_target_kind" for row in validate_runtime_program(document)["errors"])
    document = _with_concurrency()
    document["runtimeProgram"]["calls"][-1]["params"] = {}
    report = validate_runtime_program(document)
    assert not report["ok"]
    assert any(row["path"].endswith(".params.maxActive") for row in report["errors"])


def test_automatic_vertical_witness_has_exact_opt_in_wire_receipt():
    document = build_capability_witness(CAPABILITY)
    report = validate_runtime_program(document)
    assert report["ok"], report["errors"]
    compiled = compile_runtime_program(document)
    assert validate_runtime_wire(compiled)["ok"]
    receipts = [row for row in compiled["runtimeContract"]["finalWireReceipts"] if row.get("fn") == CAPABILITY]
    assert len(receipts) == 1
    assert receipts[0]["finalPath"].endswith(".spawn.maxActive")


@pytest.mark.parametrize("mutation", ["wrong_path", "wrong_value", "wrong_status", "omitted"])
def test_exact_concurrency_receipt_proof_refuses_forgery(mutation):
    document = _with_concurrency(3)
    compiled = compile_runtime_program(document)
    receipts = compiled["runtimeContract"]["finalWireReceipts"]
    receipt = next(row for row in receipts if row.get("fn") == CAPABILITY)
    if mutation == "wrong_path":
        receipt["finalPath"] = receipt["finalPath"].replace(".maxActive", ".count")
    elif mutation == "wrong_value":
        receipt["value"] = 2
    elif mutation == "wrong_status":
        receipt["status"] = "technical_projection"
    else:
        receipts.remove(receipt)
    assert not audit_compiler_receipts(receipts, authored_document=document, final_document=compiled)["ok"]
    if mutation != "omitted":  # Wire-only cannot reconstruct absent Author calls.
        assert not validate_runtime_wire(compiled)["ok"]


def test_frozen_repair_can_change_only_invalid_concurrency_leaf():
    good = _with_concurrency(6)
    broken = copy.deepcopy(good)
    broken["runtimeProgram"]["calls"][-1]["params"]["maxActive"] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": "tonic_concurrency", "paths": ["params.maxActive"]}]
    assert scope["capabilitySubset"] == [CAPABILITY]
    assert not scope["create"]["calls"]["allowed"]
    fixed_call = copy.deepcopy(good["runtimeProgram"]["calls"][-1])
    hostile_spawn = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "configure_spawn"))
    hostile_spawn["params"]["count"] = 12
    patch = {"callsUpsert": [fixed_call, hostile_spawn], "note": "Fix only invalid maxActive"}
    filtered, audit = filter_repair_patch_scope(broken, patch, scope)
    assert audit["ok"], audit
    assert audit["ignoredChanges"]
    fixed = apply_repair_patch(broken, filtered)
    assert fixed == good
    assert compile_runtime_program(fixed)["runtimeProgram"] == compile_runtime_program(good)["runtimeProgram"]


def test_unrequested_repair_cannot_add_concurrency_to_old_absent_wire():
    good = build_runtime_fixture("returning_potion")
    broken = copy.deepcopy(good)
    next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "configure_spawn")["params"]["count"] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    fixed_spawn = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "configure_spawn"))
    unsolicited_cap = _with_concurrency()["runtimeProgram"]["calls"][-1]
    filtered, audit = filter_repair_patch_scope(broken, {"callsUpsert": [fixed_spawn, unsolicited_cap], "note": "Count only"}, scope)
    assert audit["ok"], audit
    assert audit["ignoredChanges"]
    fixed = apply_repair_patch(broken, filtered)
    assert fixed == good
    assert all("maxActive" not in row.get("spawn", {}) for row in compile_runtime_program(fixed)["runtimeProgram"]["entities"])


def test_qa_tracks_nullable_reject_bounds_instead_of_omitting_new_cap():
    rows = [row for row in _runtime_param_bound_rows() if row["capability"] == CAPABILITY]
    assert len(rows) == 1
    assert rows[0]["authorBounds"] == [1, 96]
    assert rows[0]["csharpBounds"] == [1, 96]
    assert rows[0]["csharpClass"] == "RuntimeSpawnSpec"
    assert rows[0]["admission"] == "reject_without_clamp"
    assert rows[0]["preserved"]


@pytest.mark.parametrize("before,after", [
    ("value < 1", "value < 0"),
    ("value > InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner", "value > 97"),
    ("value is null || value < 1", "value < 1"),
    ("public int? MaxActive", "public int MaxActive"),
    ("[JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]", "[JsonIgnore(Condition = JsonIgnoreCondition.Never)]"),
])
def test_qa_reject_bound_scanner_refuses_changed_nullable_contract(monkeypatch, before, after):
    original = Path.read_text
    def mutant(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        return text.replace(before, after) if path.name == "RuntimeProgramSpec.cs" else text
    monkeypatch.setattr(Path, "read_text", mutant)
    rows = [row for row in _runtime_param_bound_rows() if row["capability"] == CAPABILITY]
    assert len(rows) == 1
    assert not rows[0]["preserved"]


def _assert_contact_facts(card):
    facts = json.dumps(card, ensure_ascii=False)
    assert all(term in facts for term in (
        "pierce=1", "first damaging NPC contact", "native kill", "pierce=-1",
        "does not kill from NPC contact", "on_hit", "no implicit explosion", "on_kill", "separate",
        "N tile contacts", "0.78", "collided-axis velocity", "next contact kills",
        "move_boomerang", "move_returning_glaive", "move_flail_tether", "before bounce/kill handling",
    ))


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_native_contact_return_facts_reach_serialized_author_and_repair(wire_transport, monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    parent = {"id": "literal", "name": "Literal object", "damage": 7, "useTime": 20}
    _, content, _ = build_initial_author_request(parent, parent, parent, parent, "contact-facts", model_name="test-model")
    cards = {row["fn"]: row for row in json.loads(content)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    _assert_contact_facts(cards["set_projectile_collision"])
    assert "per activation" in cards["configure_spawn"]["does"]
    assert "separate" in cards["configure_spawn"]["does"]
    assert CAPABILITY in cards["configure_spawn"]["does"]
    for driver, phrases in (
        ("move_gravity_arc", ("adds gravity", "no horizontal friction")),
        ("move_boomerang", ("wall collision", "starts return", "disables tileCollide", "does not kill")),
    ):
        assert all(term in cards[driver]["does"] for term in phrases)
        # Make only this exact driver's parameter invalid: Repair must expose
        # the same facts without replacing the selected movement or contacts.
        good = build_capability_witness(driver)
        broken = copy.deepcopy(good)
        call = next(row for row in broken["runtimeProgram"]["calls"] if row["id"] == "witness_call")
        param = next(iter(call["params"]))
        call["params"][param] = -1
        response = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["id"] == "witness_call"))
        responses, requests = wire_transport
        responses.append({"callsUpsert": [response], "realizationReplacement": good["realization"], "note": "Exact movement leaf"})
        fixed = gameplay.repair_author_item_after_failure(broken, parent, parent, parent, parent, "contact-facts", failure_report={"stage": "validation", "errors": validate_runtime_program(broken)["errors"]})
        packet = json.loads(requests[-1]["messages"][1]["content"])
        repair_card = next(row for row in packet["existingBrokenCapabilityCards"] if row["fn"] == driver)
        assert all(term in repair_card["does"] for term in phrases)
        assert compile_runtime_program(fixed)["runtimeProgram"] == compile_runtime_program(good)["runtimeProgram"]
    good = _with_concurrency(6)
    broken = copy.deepcopy(good)
    collision = next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "set_projectile_collision")
    collision["params"]["pierce"] = -2
    response = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "set_projectile_collision"))
    responses.append({"callsUpsert": [response], "realizationReplacement": good["realization"], "note": "Exact pierce"})
    fixed = gameplay.repair_author_item_after_failure(broken, parent, parent, parent, parent, "contact-facts", failure_report={"stage": "validation", "errors": validate_runtime_program(broken)["errors"]})
    packet = json.loads(requests[-1]["messages"][1]["content"])
    repair_card = next(row for row in packet["existingBrokenCapabilityCards"] if row["fn"] == "set_projectile_collision")
    _assert_contact_facts(repair_card)
    assert packet["repairScope"]["fieldPermissions"]["calls"] == [{"id": collision["id"], "paths": ["params.pierce"]}]
    assert compile_runtime_program(fixed)["runtimeProgram"] == compile_runtime_program(good)["runtimeProgram"]
    broken = copy.deepcopy(good)
    broken["runtimeProgram"]["calls"][-1]["params"]["maxActive"] = 0
    responses.append({"callsUpsert": [good["runtimeProgram"]["calls"][-1]], "realizationReplacement": good["realization"], "note": "Exact maxActive"})
    fixed = gameplay.repair_author_item_after_failure(broken, parent, parent, parent, parent, "contact-facts", failure_report={"stage": "validation", "errors": validate_runtime_program(broken)["errors"]})
    packet = json.loads(requests[-1]["messages"][1]["content"])
    assert packet["existingBrokenCapabilityCards"] == [CAPABILITY_REGISTRY[CAPABILITY].prompt_card()]
    assert packet["repairScope"]["fieldPermissions"]["calls"] == [{"id": "tonic_concurrency", "paths": ["params.maxActive"]}]
    assert compile_runtime_program(fixed)["runtimeProgram"] == compile_runtime_program(good)["runtimeProgram"]
