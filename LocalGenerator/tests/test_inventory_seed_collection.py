"""Explicit inventory passive: Author -> literal receipt -> strict delivery."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from repair_test_helpers import gameplay_repair, provider_roundtrip
from prompt_packet_helpers import request_dossier

from infini_local.core.runtime_authoring.program_schema import apply_repair_patch

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.storage.world_storage import sanitize_recipe_for_delivery

FN = "collect_seeds_from_grass"
FIELD = "collectSeedsFromGrass"


def seed_source():
    doc = build_capability_witness("configure_weapon_ammo")
    doc["runtimeProgram"]["calls"].append({"id": "seed_passive", "fn": FN, "target": "item", "params": {}})
    return doc


def test_explicit_seed_passive_survives_final_delivery_without_changing_ammo_or_costs():
    doc = seed_source()
    report = validate_runtime_program(doc)
    assert report["ok"], report
    before = deepcopy(doc)
    final = compile_runtime_program(doc)
    assert final["gameplay"][FIELD] is True
    rows = [r for r in final["runtimeContract"]["finalWireReceipts"] if r.get("fn") == FN]
    assert rows == [{"callId": "seed_passive", "fn": FN,
                     "authoredPath": f"runtimeProgram.calls[{len(doc['runtimeProgram']['calls']) - 1}].fn",
                     "finalPath": "gameplay." + FIELD, "value": True, "status": "technical_projection"}]
    assert audit_compiler_receipts(final["runtimeContract"]["finalWireReceipts"], authored_document=doc, final_document=final)["ok"]
    assert validate_runtime_wire(final)["ok"]
    delivered = sanitize_recipe_for_delivery(final)
    assert "runtimeContract" not in delivered
    assert delivered["gameplay"][FIELD] is True
    assert validate_runtime_wire(delivered)["ok"]
    baseline = sanitize_recipe_for_delivery(compile_runtime_program(build_capability_witness("configure_weapon_ammo")))
    without_passive = deepcopy(delivered)
    without_passive["gameplay"].pop(FIELD)
    assert without_passive == baseline
    assert doc == before


@pytest.mark.parametrize("value", [0, 1, "true", None, {}, []])
def test_delivered_seed_flag_is_strict_boolean(value):
    delivered = sanitize_recipe_for_delivery(compile_runtime_program(seed_source()))
    delivered["gameplay"][FIELD] = value
    report = validate_runtime_wire(delivered)
    assert not report["ok"], report
    assert any(row["path"] == "$.gameplay." + FIELD for row in report["errors"])


@pytest.mark.parametrize("source_available", [True, False])
@pytest.mark.parametrize("mutation", ["drop", "duplicate", "type", "value", "source", "owner", "path"])
def test_seed_literal_receipt_requires_unique_exact_fn_owner(mutation, source_available):
    doc = seed_source()
    final = compile_runtime_program(doc)
    rows = final["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in rows if r.get("fn") == FN)
    if mutation == "drop":
        rows.remove(row)
    elif mutation == "duplicate":
        rows.append(deepcopy(row))
    elif mutation in {"type", "value"}:
        row["value"] = 1 if mutation == "type" else False
        final["gameplay"][FIELD] = row["value"]
    elif mutation == "source":
        row["authoredPath"] = row["authoredPath"].replace(".fn", ".params.enabled")
    elif mutation == "owner":
        row["fn"] = "configure_weapon_ammo"
    else:
        row["finalPath"] = "runtimeProgram.entities[0]." + FIELD
        final["runtimeProgram"]["entities"][0][FIELD] = True
    assert not audit_compiler_receipts(rows, authored_document=doc if source_available else None, final_document=final)["ok"]
    assert not validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("mutation", ["parameter", "projectile", "duplicate"])
def test_seed_author_rejects_unsupported_params_targets_and_duplicate_slot(mutation):
    doc = seed_source()
    call = doc["runtimeProgram"]["calls"][-1]
    if mutation == "parameter":
        call["params"]["chancePercent"] = 100
    elif mutation == "projectile":
        call["target"] = "witness_entity"
    else:
        doc["runtimeProgram"]["calls"].append({**deepcopy(call), "id": "duplicate_seed"})
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


def test_sparse_seed_call_is_the_same_exact_opt_in_and_absence_stays_inactive():
    doc = seed_source()
    doc["runtimeProgram"]["calls"][-1] = {"id": "seed_passive", "fn": FN}
    assert validate_runtime_program(doc)["ok"]
    assert sanitize_recipe_for_delivery(compile_runtime_program(doc))["gameplay"][FIELD] is True
    doc["runtimeProgram"]["calls"].pop()
    absent = sanitize_recipe_for_delivery(compile_runtime_program(doc))
    assert FIELD not in absent["gameplay"]
    absent["gameplay"][FIELD] = False
    assert validate_runtime_wire(absent)["ok"]


def test_seed_witness_is_inventory_only_without_active_use_or_binding():
    doc = build_capability_witness(FN)
    assert not doc["runtimeProgram"]["bindings"]
    assert {c["fn"] for c in doc["runtimeProgram"]["calls"]} == {"configure_item_stats", FN}
    assert validate_runtime_program(doc)["ok"]
    assert validate_runtime_wire(compile_runtime_program(doc))["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_real_author_packet_exposes_explicit_inventory_capability_without_inheritance(monkeypatch, mode):
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = build_initial_author_request({"dropSeedsIfInInventory": True}, {}, "offline", model_name="offline-no-model")
    dossier = request_dossier(request)
    card = next(c for c in dossier["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == FN)
    assert card["params"] == {}
    assert "Inventory passive" in json.dumps(card)
    packet = json.dumps(request)
    assert "collect_seeds_from_grass" in packet
    assert "only by explicit" in packet
    assert "not executable support for that behavior" not in packet
    doc = seed_source()
    if mode != "off":
        provider_roundtrip(doc, request["response_format"])
    # Parent facts do not inject a call; absent explicit selection remains absent.
    baseline = build_capability_witness("configure_weapon_ammo")
    assert FIELD not in compile_runtime_program(baseline)["gameplay"]


@pytest.mark.parametrize("present", [True, False])
@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_leaf_repair_freezes_seed_selection_or_absence(monkeypatch, present, mode):
    doc = seed_source() if present else build_capability_witness("configure_weapon_ammo")
    stats = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")
    stats["params"]["damage"] = True
    fixed = deepcopy(stats)
    fixed["params"]["damage"] = 37
    expected = apply_repair_patch(doc, {"note": "fix damage only", "callsUpsert": [fixed]})
    hostile = deepcopy(seed_source()["runtimeProgram"]["calls"][-1])
    hostile["fn"] = "recall_home_on_use" if present else FN
    hostile["params"] = {"cooldownSeconds": 1.5} if present else {}
    repaired, dossier = gameplay_repair(monkeypatch, doc, {"note": "hostile seed change", "callsUpsert": [fixed, hostile]}, mode, out_of_scope_response=True)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": stats["id"], "paths": ["params.damage"]}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert repaired == expected
    final = sanitize_recipe_for_delivery(compile_runtime_program(repaired))
    assert final["gameplay"].get(FIELD, False) is present
    assert validate_runtime_wire(final)["ok"]


def test_inventory_passive_generated_docs_do_not_claim_a_binding():
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "tools/generate_low_level_runtime_docs.py"
    spec = importlib.util.spec_from_file_location("seed_doc_owner", path)
    assert spec is not None and spec.loader is not None
    docs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(docs)
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    text = docs.event_input_cell(CAPABILITY_REGISTRY[FN])
    assert "inventory query" in text and "no binding" in text


def test_native_seed_dto_keeps_nullable_omitted_storage_for_old_definition_identity():
    from infini_local.qa.primitive_loss_audit import _PARSER, _nodes, item_gameplay_surface_audit
    source = (Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal/Common/Models/Contracts/GeneratedItemData.Model.cs").read_bytes()
    properties = [node for node in _nodes(_PARSER.parse(source).root_node, "property_declaration")
                  if (name := node.child_by_field_name("name")) is not None
                  and source[name.start_byte:name.end_byte] == b"CollectSeedsFromGrass"]
    assert len(properties) == 1
    prop = properties[0]
    storage = prop.child_by_field_name("type")
    assert source[storage.start_byte:storage.end_byte] == b"bool?", "inactive semantics must not materialize false into old definition bytes"
    text = source[prop.start_byte:prop.end_byte]
    assert b"JsonIgnoreCondition.WhenWritingNull" in text
    assert b"throw new InvalidDataException" in text, "present null is not an authored boolean"
    assert item_gameplay_surface_audit(source)["ok"]


def test_committed_native_fixture_preserves_compiler_delivery_in_headless_mode():
    actual = sanitize_recipe_for_delivery(compile_runtime_program(seed_source()))
    # The compiler emits mechanics, not a completed image stage. Declare this
    # CPU-only fixture honestly and fix identity so pre/post native hashes are
    # comparable; do not counterfeit ready PNG status or let the DTO invent IDs.
    actual.update(sourceMode="test_fixture", id="g_1122334455667788",
                  recipeKey="inventory_seed_native_fixture")
    # This fixture exercises inventory queries, never art/drawing. Supply an
    # explicit no-image choice rather than an incomplete pre-Visual asset mode.
    for entity in actual["runtimeProgram"]["entities"]:
        entity["visual"]["assetMode"] = "no_asset"
    fixture = Path(__file__).resolve().parents[2] / "tools/fixtures/inventory-seed-collection.json"
    assert json.loads(fixture.read_text()) == actual
