"""Canonical gameplay choices preserve captured mechanics, not retired item envelopes."""
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, capability_for_saved_receipt
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

_CAPTURE = json.loads(gzip.decompress((Path(__file__).parent / "fixtures" / "gameplay_vocabulary_wire_baseline.json.gz").read_bytes()))


def executable_wire(document):
    result = deepcopy(document)
    result.pop("runtimeContract")
    return result


def current_vocabulary_source(captured):
    """Named test control: retain every choice except the retired visibility alias."""
    source = deepcopy(captured)
    for call in source["runtimeProgram"]["calls"]:
        if call["fn"] == "item_use" and "customHeldSprite" in call["params"]:
            assert call["params"].pop("customHeldSprite") == "hidden"
            call["params"]["hideUseGraphic"] = True
    return source


def current_vocabulary_wire_control(captured):
    wire = executable_wire(captured)
    if "releaseTiming" in wire.get("gameplay", {}):
        assert wire["gameplay"].pop("releaseTiming") == "immediate"
        assert wire["runtimeProgram"]["itemUse"].pop("releaseTiming") == "immediate"
        wire["runtimeProgram"]["itemUse"]["hideUseGraphic"] = True
    return wire


def assert_archived_vocabulary_boundary(wire):
    retired = "releaseTiming" in wire.get("runtimeProgram", {}).get("itemUse", {})
    report = validate_runtime_wire(wire)
    assert report["ok"] is not retired
    if retired:
        assert any(e["path"] == "$.runtimeProgram.itemUse.releaseTiming" for e in report["errors"])
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"] is not retired


@pytest.mark.parametrize("case", _CAPTURE["cases"], ids=lambda row: row["previousFn"])
def test_canonical_choices_preserve_captured_execution_in_current_visibility_envelope(case):
    before = deepcopy(case)
    source = current_vocabulary_source(case["author"])
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    actual = executable_wire(wire)
    expected = current_vocabulary_wire_control(case["wire"])
    if case["previousFn"] == "set_projectile_beam_geometry":
        # New fresh compilation declares one neutral origin leaf. Keep the
        # frozen old capture byte-for-byte; compare every retained field exactly.
        call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "beam_geometry")
        assert "startOffsetBlocks" not in call["params"]
        fresh = next(row for row in actual["runtimeProgram"]["entities"] if row["id"] == call["target"])
        old = next(row for row in expected["runtimeProgram"]["entities"] if row["id"] == call["target"])
        assert "startOffsetPx" not in old["beamGeometry"]
        neutral = fresh["beamGeometry"].pop("startOffsetPx")
        assert type(neutral) in (int, float) and neutral == 0
    assert actual == expected
    assert validate_runtime_wire(wire)["ok"]
    assert_archived_vocabulary_boundary(case["wire"])
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)["ok"]
    assert case == before


def test_capture_covers_every_visible_capability_and_old_identity_is_not_an_author_alias():
    covered = {capability_for_saved_receipt(row["previousFn"]).name for row in _CAPTURE["cases"]}
    assert covered == {name for name, cap in CAPABILITY_REGISTRY.items() if cap.author_visible}
    for row in _CAPTURE["cases"]:
        cap = capability_for_saved_receipt(row["previousFn"])
        if cap.name == row["previousFn"]:
            continue
        source = current_vocabulary_source(row["author"])
        call = next(call for call in source["runtimeProgram"]["calls"] if call["fn"] == cap.name)
        call["fn"] = row["previousFn"]
        assert not validate_runtime_program(source)["ok"]
        assert row["previousFn"] not in CAPABILITY_REGISTRY


@pytest.mark.parametrize("value", [0, 1, 128, 255])
def test_transparency_byte_is_exact_existing_native_domain(value):
    case = next(row for row in _CAPTURE["cases"] if row["previousFn"] == "set_projectile_opacity")
    source = current_vocabulary_source(case["author"])
    call = next(call for call in source["runtimeProgram"]["calls"] if call["fn"] == "set_opacity")
    call["params"]["transparencyByte"] = value
    wire = compile_runtime_program(source)
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    assert entity["opacity"]["alpha"] == value
    call["params"]["alpha"] = call["params"].pop("transparencyByte")
    assert not validate_runtime_program(source)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("previous_fn", ["apply_generated_buff_on_use", "spawn_entity_on_event", "seek_projectile"])
def test_saved_generated_parent_keeps_old_wire_in_next_craft_with_current_unit_guide(monkeypatch, mode, previous_fn):
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier
    case = next(row for row in _CAPTURE["cases"] if row["previousFn"] == previous_fn)
    parent = {"name": "accepted saved craft", "generatedData": deepcopy(case["wire"])}
    before = deepcopy(parent)
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = build_initial_author_request(parent, parent, "old-wire-next-craft", model_name="offline")
    packet = request_dossier(request)
    for side in ("A", "B"):
        source = packet["parents"][side]["packet"]["raw"]["generatedParent"]
        assert source["gameplay"] == case["wire"]["gameplay"]
        expected = deepcopy(case["wire"]["runtimeProgram"])
        for entity in expected["entities"]:
            entity.pop("visual", None)
        assert source["runtimeProgram"] == expected
    assert request["response_format"]["type"] == mode
    assert packet["runtimeCapabilityContract"]["catalog"]["authoringSchema"] == "infini.runtime-program.authoring.v7"
    assert parent == before


@pytest.mark.parametrize("case", _CAPTURE["combatCases"], ids=lambda row: row["activation"])
def test_equipment_aligned_combat_names_keep_scoped_mechanics_and_archive_boundary(case):
    before = deepcopy(case)
    source = current_vocabulary_source(case["author"])
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    assert executable_wire(wire) == current_vocabulary_wire_control(case["wire"])
    assert_archived_vocabulary_boundary(case["wire"])
    assert not validate_runtime_program(case["previousAuthor"])["ok"]
    assert not audit_compiler_receipts(case["wire"]["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=case["wire"])["ok"]
    assert case == before


def test_common_combat_names_have_explicit_units_without_changing_numeric_projection():
    cap = CAPABILITY_REGISTRY["generated_buff_on_use"]
    card = cap.author_prompt_card()["params"]["combat"]["properties"]
    for key, units, old in (("attackSpeedBonus", "additive_percent", "attackSpeedPercent"),
                            ("critChance", "percentage_points", "critChancePoints"),
                            ("damageBonus", "additive_percent", "damagePercent")):
        spec = cap.params["combat"].properties[key]
        assert card[key]["units"] == units
        assert spec.wire_name == "combat." + old
        for value in (spec.minimum, 0, spec.maximum):
            assert spec.to_wire(value) == value
        assert old not in card
