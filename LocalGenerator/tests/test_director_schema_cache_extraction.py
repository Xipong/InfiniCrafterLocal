"""Offline literal grammar and native serialization witnesses for Director caches."""

from infini_local.core.vfx import contract as vfx_contract
from infini_local.core.vfx import repair as vfx_repair
from infini_local.core.vfx import schema as vfx_schema
from infini_local.pipelines.visual import contract as visual_contract
from infini_local.core import provider_schema

import copy
import json

import pytest

from infini_local.core.vfx.materials import vfx_model_schema, vfx_model_payload

from infini_local.core.llm_prompt_cache import (
    with_instruction_segments, with_schema_instruction_definitions,
)


def test_explicit_owner_paths_share_one_identical_definition_without_mutation():
    leaf = {"type": "number", "minimum": 0.25, "maximum": 4.0, "description": "Exact scale."}
    schema = {"type": "object", "properties": {"a": leaf, "b": copy.deepcopy(leaf)}}
    dossier = {"rules": ["Preserve every rule."], "outputSchema": schema, "repairScope": {"paths": ["a"]}}
    payload = with_instruction_segments({"messages": [
        {"role": "system", "content": "contract"}, {"role": "user", "content": "{}"},
    ], "response_format": {"type": "json_schema", "json_schema": {"schema": schema}}}, dossier, ("rules",))
    before = copy.deepcopy(payload)
    extracted = with_schema_instruction_definitions(payload, "outputSchema", {
        "scale": (("properties", "a"), ("properties", "b")),
    })
    assert payload == before
    static, dynamic = [json.loads(row["content"]) for row in extracted["messages"][1:]]
    assert static["schemaDefinitions"] == {"$defs": {"scale": leaf}}
    assert dynamic["outputSchema"]["properties"] == {
        "a": {"$ref": "#/$defs/scale"}, "b": {"$ref": "#/$defs/scale"},
    }
    assert dynamic["repairScope"] == dossier["repairScope"]
    assert extracted["response_format"] == before["response_format"]


@pytest.mark.parametrize("selection", [
    (), ((),), (("properties", "a"), ("properties", "b")),
    (("properties", "a"), ("properties", "a")),
])
def test_explicit_definition_paths_reject_empty_unequal_or_overlapping_nodes(selection):
    dossier = {"rules": [], "outputSchema": {"properties": {
        "a": {"type": "number"}, "b": {"type": "integer"},
    }}, "case": "user"}
    payload = with_instruction_segments({"messages": [
        {"role": "system", "content": "contract"}, {"role": "user", "content": "{}"},
    ]}, dossier, ("rules",))
    before = copy.deepcopy(payload)
    with pytest.raises(ValueError):
        with_schema_instruction_definitions(payload, "outputSchema", {"number": selection})
    assert payload == before


def test_shared_definition_rejects_equal_numbers_with_different_json_literals():
    dossier = {"rules": [], "outputSchema": {"properties": {
        "a": {"type": "number", "minimum": 1},
        "b": {"type": "number", "minimum": 1.0},
    }}, "case": "user"}
    payload = with_instruction_segments({"messages": [
        {"role": "system", "content": "contract"}, {"role": "user", "content": "{}"},
    ]}, dossier, ("rules",))
    with pytest.raises(ValueError, match="literally identical"):
        with_schema_instruction_definitions(payload, "outputSchema", {
            "number": (("properties", "a"), ("properties", "b")),
        })


def _packet(monkeypatch, stage, fixture, mode, *, captured=None, vfx_source=None):
    from test_craft_instruction_segments import stage_packets
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    import vfx_material_fixtures
    from test_low_level_three_stage_pipeline import _vfx_output
    data = (vfx_material_fixtures._data("beam_geometry") if fixture == "beam_geometry"
            else compile_runtime_program(build_runtime_fixture(fixture)))
    with monkeypatch.context() as mp:
        mp.setattr(vfx_material_fixtures, "_data", lambda: copy.deepcopy(data))
        mp.setattr(vfx_material_fixtures, "_legacy", lambda current: copy.deepcopy(vfx_source) if vfx_source is not None else _vfx_output(current))
        if captured is not None:
            from infini_local.pipelines.vfx import request as sender
            import infini_local.pipelines.visual.request as visual_request
            def record(payload, dossier, static_keys):
                # Observe the actual builder before optional schema extraction.
                # Scoped Visual Repair deliberately does not call the extractor.
                segmented = with_instruction_segments(payload, dossier, static_keys)
                captured.append(copy.deepcopy(segmented))
                return segmented
            mp.setattr(visual_request, "with_instruction_segments", record)
            mp.setattr(sender, "with_instruction_segments", record)
        return stage_packets(mp, stage, format_mode=mode, labels=("novel-a",))[0], data


def _assert_visual_size_repair_packet(packet, data, mode):
    from jsonschema import Draft202012Validator
    from prompt_packet_helpers import request_dossier
    from test_visual_presentation_metadata import _visual_kit

    dossier = request_dossier(packet)
    static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
    assert "schemaDefinitions" not in static
    assert dossier["repairScope"]["fieldPermissions"] == {
        "itemPaths": ["renderSizePx"], "equipOverlayPaths": [], "entities": [],
    }
    # Only the canonical editable leaf is offered; valid equipment and entities
    # remain USER-owned frozen context even when the initial contract needs them.
    full = visual_contract._visual_repair_schema([row["id"] for row in data["runtimeProgram"]["entities"]])
    leaf = full["properties"]["itemPatch"]["anyOf"][0]["properties"]["renderSizePx"]
    expected = {"type": "object", "additionalProperties": False, "properties": {
        "schema": full["properties"]["schema"], "note": full["properties"]["note"],
        "itemPatch": {"anyOf": [{"type": "object", "additionalProperties": False,
            "properties": {"renderSizePx": leaf}, "required": ["renderSizePx"]}, {"type": "null"}]},
    }, "required": ["schema", "note", "itemPatch"]}
    if mode == "json_schema":
        expected = provider_schema._provider_strict_projection(expected)
        assert packet["response_format"]["json_schema"]["schema"] == expected
    assert dynamic["responseSchema"] == dossier["responseSchema"] == expected
    source = _visual_kit(data)
    assert dossier["brokenFragments"]["item"] == dict(source["item"], renderSizePx=None)
    assert dossier["validGeneratedContext"]["entities"] == source["entities"]
    assert dossier["validGeneratedContext"]["equipOverlay"] == source.get("equipOverlay")
    valid = {"schema": visual_contract.VISUAL_REPAIR_PATCH_SCHEMA, "note": "size only", "itemPatch": {"renderSizePx": 48}}
    assert Draft202012Validator(expected).is_valid(valid)
    for hostile in (dict(valid, entitiesUpsert=[]), dict(valid, equipOverlayPatch={}),
                    dict(valid, itemPatch={"renderSizePx": True}),
                    dict(valid, itemPatch={"renderSizePx": 48, "prompt": "rewrite"})):
        assert not Draft202012Validator(expected).is_valid(hostile)


def _assert_vfx_alpha_repair_packet(packet, data, mode):
    from jsonschema import Draft202012Validator
    from prompt_packet_helpers import request_dossier
    from test_low_level_three_stage_pipeline import _vfx_output

    static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
    source = vfx_model_payload(_vfx_output(data))
    dossier = request_dossier(packet)
    schema = dossier["outputSchema"]
    assert set(schema["properties"]) == {"schema", "note", "slotsUpsert"}
    assert dossier["repairScope"]["fieldPermissions"] == {
        "globals": {}, "slots": [{"slotId": source["slots"][0]["id"], "paths": ["alpha"]}], "assets": [],
    }
    canonical = vfx_schema._director_schema(data)["properties"]["slots"]["items"]
    slot = schema["properties"]["slotsUpsert"]["items"]
    assert schema["properties"]["slotsUpsert"]["maxItems"] == 1
    assert slot["properties"]["alpha"] == canonical["properties"]["alpha"]
    assert set(slot["properties"]) == set(source["slots"][0])
    for field, value in source["slots"][0].items():
        if field == "alpha":
            continue
        frozen = slot["properties"][field]
        assert frozen["const"] == value
        assert "type" in frozen
        assert Draft202012Validator(frozen).is_valid(value)
        assert not Draft202012Validator(frozen).is_valid({"foreign": "literal"})
        if field == "id":
            assert frozen == {**canonical["properties"]["id"], "const": value}
    assert static["schemaDefinitions"] == {"$defs": {"slot_alpha": canonical["properties"]["alpha"]}}
    assert dynamic["outputSchema"]["properties"]["slotsUpsert"]["items"]["properties"]["alpha"] == {"$ref": "#/$defs/slot_alpha"}
    assert dossier["brokenFragments"]["slots"] == [dict(source["slots"][0], alpha=None)]
    valid = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "alpha only", "slotsUpsert": source["slots"]}
    assert Draft202012Validator(schema).is_valid(valid)
    for hostile in (dict(valid, assetsUpsert=[]), dict(valid, slotIdsDelete=[]),
                    dict(valid, slotsUpsert=[dict(source["slots"][0], alpha=True)]),
                    dict(valid, slotsUpsert=[dict(source["slots"][0], scale=4)])):
        assert not Draft202012Validator(schema).is_valid(hostile)
    if mode == "json_schema":
        wire_schema = packet["response_format"]["json_schema"]["schema"]
        assert wire_schema == provider_schema._provider_strict_projection(
            provider_schema.defer_provider_cross_field_constraints(schema), omit_annotations=True,
        )
        assert Draft202012Validator(wire_schema).is_valid(valid)
        assert not Draft202012Validator(wire_schema).is_valid(dict(valid, slotIdsDelete=[]))


@pytest.mark.parametrize("stage", ["visual", "visual_repair"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_visual_caches_literal_entity_grammar_not_roster(monkeypatch, stage, mode):
    from prompt_packet_helpers import request_dossier
    packets = []
    for fixture in ("workbench_blade", "door_on_chain", "beam_geometry"):
        packet, data = _packet(monkeypatch, stage, fixture, mode)
        if stage.endswith("repair"):
            _assert_visual_size_repair_packet(packet, data, mode)
            packets.append(packet)
            continue
        static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
        key = "entitiesUpsert" if stage.endswith("repair") else "entities"
        union = "anyOf" if mode == "json_schema" else "oneOf"
        branches = dynamic["responseSchema"]["properties"][key]["items"][union]
        for branch in branches:
            assert branch["properties"]["scale"] == {"$ref": "#/$defs/entityScale"}
        for field in ("prompt", "silhouette", "visualIdentity"):
            assert field not in branches[0]["properties"]
            assert branches[1]["properties"][field] == {"$ref": "#/$defs/entity_" + field}
        if stage.endswith("repair"):
            assert "animationPlan" not in dynamic["responseSchema"]["properties"]
        else:
            assert dynamic["responseSchema"]["properties"]["animationPlan"] == {"$ref": "#/$defs/animationPlan"}
        ids = [row["id"] for row in data["runtimeProgram"]["entities"]]
        canonical = (visual_contract._visual_repair_schema if stage.endswith("repair") else visual_contract._response_schema)(ids, False, data["runtimeProgram"]["itemEntityId"])
        if mode == "json_schema":
            canonical = provider_schema._provider_strict_projection(canonical)
            assert packet["response_format"]["json_schema"]["schema"] == canonical
        assert request_dossier(packet)["responseSchema"] == canonical
        assert branches[0]["properties"]["entityId"]["enum"] == [data["runtimeProgram"]["itemEntityId"]]
        assert branches[1]["properties"]["entityId"]["enum"] == ids[1:]
        assert set(static["schemaDefinitions"]["$defs"]) >= {"entityScale", "entity_prompt", "entity_silhouette", "entity_visualIdentity"}
        packets.append(packet)
    assert packets[0]["messages"][:2] == packets[1]["messages"][:2] == packets[2]["messages"][:2]
    assert len({p["messages"][2]["content"] for p in packets}) == 3


@pytest.mark.parametrize("stage", ["visual", "visual_repair"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
@pytest.mark.parametrize("overlay", [False, True])
def test_visual_item_only_roster_preserves_optional_equipment_contract(monkeypatch, stage, mode, overlay):
    from test_craft_instruction_segments import stage_packets
    from prompt_packet_helpers import request_dossier
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.qa.capability_witnesses import build_capability_witness
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from test_stable_schema_data import capture_wire
    import vfx_material_fixtures

    data = compile_runtime_program(build_runtime_fixture("equipment_tool_combat") if overlay else build_capability_witness("tool_stats"))
    before = copy.deepcopy(data)
    assert len(data["runtimeProgram"]["entities"]) == 1
    monkeypatch.setattr(vfx_material_fixtures, "_data", lambda: copy.deepcopy(data))
    packet, = stage_packets(monkeypatch, stage, format_mode=mode, labels=("novel-a",))
    ids = [data["runtimeProgram"]["itemEntityId"]]
    if stage.endswith("repair"):
        _assert_visual_size_repair_packet(packet, data, mode)
        assert "equipOverlayPatch" not in request_dossier(packet)["responseSchema"]["properties"]
        assert data == before
        context = {"provider": "openai_codex", "base_url": "https://chatgpt.com/backend-api/codex", "api_mode": "responses", "model": "gpt-6.1-sol"}
        wire = capture_wire(monkeypatch, packet, context)
        assert wire["prompt_cache_key"] and wire["instructions"] == packet["messages"][0]["content"]
        return
    canonical = (visual_contract._visual_repair_schema if stage.endswith("repair") else visual_contract._response_schema)(ids, overlay, ids[0])
    if mode == "json_schema":
        canonical = provider_schema._provider_strict_projection(canonical)
        assert packet["response_format"]["json_schema"]["schema"] == canonical
    assert request_dossier(packet)["responseSchema"] == canonical
    static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
    slot = dynamic["responseSchema"]["properties"]["entitiesUpsert" if stage.endswith("repair") else "entities"]["items"]
    assert slot["properties"]["entityId"]["enum"] == ids
    assert slot["properties"]["scale"] == {"$ref": "#/$defs/entityScale"}
    overlay_key = "equipOverlayPatch" if stage.endswith("repair") else "equipOverlay"
    assert (overlay_key in canonical["properties"]) is overlay
    assert "schemaDefinitions" in static and data == before
    context = {"provider": "openai_codex", "base_url": "https://chatgpt.com/backend-api/codex", "api_mode": "responses", "model": "gpt-6.1-sol"}
    wire = capture_wire(monkeypatch, packet, context)
    assert wire["prompt_cache_key"] and wire["instructions"] == packet["messages"][0]["content"]


@pytest.mark.parametrize("stage", ["vfx", "vfx_repair"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_vfx_caches_owned_slot_grammar_not_dynamic_compatibility(monkeypatch, stage, mode):
    from prompt_packet_helpers import request_dossier
    packets = []
    for fixture in ("workbench_blade", "door_on_chain", "beam_geometry"):
        packet, data = _packet(monkeypatch, stage, fixture, mode)
        if stage.endswith("repair"):
            _assert_vfx_alpha_repair_packet(packet, data, mode)
            packets.append(packet)
            continue
        static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
        repair = stage.endswith("repair")
        key = "slotsUpsert" if repair else "slots"
        schema = dynamic["outputSchema"]
        slot = schema["properties"][key]["items"]
        assert slot["properties"]["rendererKind"] == {"$ref": "#/$defs/slot_rendererKind"}
        assert schema["properties"]["assetsUpsert" if repair else "assets"]["items"] == {"$ref": "#/$defs/asset"}
        for field in ("element", "path", "screenShake", "particle", "sound"):
            assert slot["properties"][field] == {"$ref": "#/$defs/" + field}
        canonical = vfx_model_schema((vfx_repair.vfx_repair_schema if repair else vfx_schema._director_schema)(data))
        assert request_dossier(packet)["outputSchema"] == canonical
        if mode == "json_schema":
            assert packet["response_format"]["json_schema"]["schema"] == provider_schema._provider_strict_projection(
                provider_schema.defer_provider_cross_field_constraints(canonical), omit_annotations=True,
            )
        original_slot = canonical["properties"][key]["items"]
        for field in ("entityId", "event"):
            assert slot["properties"][field] == original_slot["properties"][field]
        assert slot["allOf"] == original_slot["allOf"]
        assert not any(key.startswith("rendererRule_") for key in static["schemaDefinitions"]["$defs"])
        packets.append(packet)
    assert packets[0]["messages"][:2] == packets[1]["messages"][:2] == packets[2]["messages"][:2]
    assert len({p["messages"][2]["content"] for p in packets}) == 3

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("offline cache extraction attempted network"))


@pytest.mark.parametrize("stage", ["visual", "visual_repair", "vfx", "vfx_repair"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_actual_native_serialization_is_static_across_three_rosters_with_exact_dossier(monkeypatch, stage, mode):
    from test_stable_schema_data import capture_wire, wire_text
    from prompt_packet_helpers import request_dossier
    context = {"provider": "openai_codex", "base_url": "https://chatgpt.com/backend-api/codex",
               "api_mode": "responses", "model": "gpt-6.1-sol"}
    wires = []
    for fixture in ("workbench_blade", "door_on_chain", "beam_geometry"):
        captured = []
        packet, _ = _packet(monkeypatch, stage, fixture, mode, captured=captured)
        before = copy.deepcopy(packet)
        assert len(captured) == 1, "observe the real builder once, including non-extracted Repair"
        assert request_dossier(packet) == request_dossier(captured[0])
        assert json.dumps(request_dossier(packet), ensure_ascii=False, separators=(",", ":")) == json.dumps(
            request_dossier(captured[0]), ensure_ascii=False, separators=(",", ":"),
        )
        original_static = json.loads(captured[0]["messages"][1]["content"])
        static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
        if "schemaDefinitions" in static:
            assert static["rules"][:-1] == original_static["rules"]
        else:
            assert stage == "visual_repair"
            assert static == original_static
            assert packet["messages"] == captured[0]["messages"]
        for key in original_static.keys() - {"rules"}:
            assert static[key] == original_static[key]
        original_dynamic = json.loads(captured[0]["messages"][2]["content"])
        for key in original_dynamic.keys() - {"responseSchema", "outputSchema"}:
            assert dynamic[key] == original_dynamic[key]
        assert packet["response_format"] == captured[0]["response_format"]
        wire = capture_wire(monkeypatch, packet, context)
        assert packet == before
        assert wire["instructions"] == packet["messages"][0]["content"]
        rows = [row for row in wire["input"] if wire_text(row) != "JSON response."]
        assert [(row["role"], wire_text(row)) for row in rows] == [
            (row["role"], row["content"]) for row in packet["messages"][1:]
        ]
        if mode == "json_schema":
            assert wire["text"]["format"]["schema"] == packet["response_format"]["json_schema"]["schema"]
            assert '"$ref"' not in json.dumps(wire["text"]["format"]["schema"])
        wires.append(wire)
    assert len({wire["instructions"] for wire in wires}) == 1
    assert len({json.dumps([row for row in wire["input"] if row["role"] == "developer"], ensure_ascii=False) for wire in wires}) == 1
    assert len({json.dumps([row for row in wire["input"] if row["role"] == "user"], ensure_ascii=False) for wire in wires}) == 3
    assert len({wire["prompt_cache_key"] for wire in wires}) == 1
    changed = copy.deepcopy(packet)
    static["rules"].append("Canonical grammar revision.")
    changed["messages"][1]["content"] = json.dumps(static, ensure_ascii=False, separators=(",", ":"))
    assert capture_wire(monkeypatch, changed, context)["prompt_cache_key"] != wires[-1]["prompt_cache_key"]

@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_vfx_cache_tracks_exact_scope_but_not_source_specific_constants(monkeypatch, mode):
    from prompt_packet_helpers import request_dossier
    from test_stable_schema_data import capture_wire
    from vfx_material_fixtures import _data
    from test_low_level_three_stage_pipeline import _vfx_output

    data = _data()
    first = _vfx_output(data)
    second = copy.deepcopy(first)
    second["slots"][0]["duration"] = 30
    # _packet diagnoses alpha=None. The co-diagnosed duration in the third source
    # changes the exact grammar, not a supposedly universal cache definition.
    third = copy.deepcopy(first)
    third["slots"][0]["duration"] = True
    packets = [_packet(monkeypatch, "vfx_repair", "workbench_blade", mode, vfx_source=source)[0]
               for source in (first, second, third)]
    static = [json.loads(packet["messages"][1]["content"]) for packet in packets]
    assert packets[0]["messages"][:2] == packets[1]["messages"][:2]
    assert static[0]["schemaDefinitions"] == static[1]["schemaDefinitions"]
    canonical = vfx_schema._director_schema(data)["properties"]["slots"]["items"]["properties"]
    assert static[0]["schemaDefinitions"]["$defs"] == {"slot_alpha": canonical["alpha"]}
    assert static[2]["schemaDefinitions"]["$defs"] == {
        "slot_alpha": canonical["alpha"], "slot_duration": canonical["duration"],
    }
    for packet, value in zip(packets[:2], (20, 30)):
        dossier = request_dossier(packet)
        row = dossier["outputSchema"]["properties"]["slotsUpsert"]["items"]
        assert row["properties"]["duration"] == {"const": value, "type": "number" if type(value) is float else "integer"}
        assert dossier["brokenFragments"]["slots"][0]["duration"] == value
    context = {"provider": "openai_codex", "base_url": "https://chatgpt.com/backend-api/codex",
               "api_mode": "responses", "model": "gpt-6.1-sol"}
    wires = [capture_wire(monkeypatch, packet, context) for packet in packets]
    assert wires[0]["prompt_cache_key"] == wires[1]["prompt_cache_key"]
    assert wires[0]["prompt_cache_key"] != wires[2]["prompt_cache_key"]


@pytest.mark.parametrize("stage,mode", [
    pytest.param("visual", "json_schema", id="visual-nullable-schema"),
    pytest.param("visual_repair", "json_object", id="visual-repair-json"),
    pytest.param("vfx", "off", id="vfx-unformatted"),
    pytest.param("vfx_repair", "json_schema", id="vfx-repair-schema"),
])
def test_reference_schema_reconstructs_owner_admission_and_refusal(monkeypatch, stage, mode):
    from jsonschema import Draft202012Validator
    from infini_local.core.schema_validation import strict_schema_errors
    import infini_local.core.vfx.contract as vfx_contract
    from test_visual_presentation_metadata import _visual_kit
    from test_codex_subscription_contract import _encode_nullable_fixture
    from vfx_material_fixtures import _sprite
    from prompt_packet_helpers import request_dossier
    packet, data = _packet(monkeypatch, stage, "workbench_blade", mode)
    static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
    visual_stage = stage.startswith("visual")
    repair = stage.endswith("repair")
    key = "responseSchema" if visual_stage else "outputSchema"
    compact = copy.deepcopy(dynamic[key])
    if "schemaDefinitions" in static:
        compact["$defs"] = static["schemaDefinitions"]["$defs"]
    else:
        assert stage == "visual_repair"
        assert '"$ref"' not in json.dumps(compact)
    inline = request_dossier(packet)[key]
    if mode == "json_schema":
        expected_wire = inline if visual_stage else provider_schema._provider_strict_projection(
            provider_schema.defer_provider_cross_field_constraints(inline), omit_annotations=True,
        )
        assert expected_wire == packet["response_format"]["json_schema"]["schema"]
    if visual_stage:
        valid = ({"schema": visual_contract.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": {"renderSizePx": 48},
                  "note": "one leaf"} if repair else _visual_kit(data))
        if mode == "json_schema":
            ids = [e["id"] for e in data["runtimeProgram"]["entities"]]
            local = visual_contract._response_schema(ids, False, data["runtimeProgram"]["itemEntityId"])
            valid = _encode_nullable_fixture(valid, local)
        invalid = copy.deepcopy(valid)
        invalid["itemPatch" if repair else "item"]["renderSizePx" if repair else "inventoryScale"] = True
        unknown = copy.deepcopy(valid)
        if repair:
            unknown["entityIdsDelete"] = ["not_in_roster"]
        else:
            unknown["entities"][0]["entityId"] = "not_in_roster"
    else:
        valid = _sprite(data)
        if repair:
            from test_low_level_three_stage_pipeline import _vfx_output
            valid = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "one leaf", "slotsUpsert": _vfx_output(data)["slots"]}
        valid = vfx_model_payload(valid)
        slot_key = "slotsUpsert" if repair else "slots"
        invalid = copy.deepcopy(valid)
        if repair:
            invalid[slot_key][0]["alpha"] = True
        else:
            invalid[slot_key][0]["element"]["count"] = True
        unknown = copy.deepcopy(valid)
        unknown[slot_key][0]["event"] = "not_in_runtime_events"
    Draft202012Validator.check_schema(compact)
    for candidate, expected in ((valid, True), (invalid, False), (unknown, False), ({}, False), (None, False)):
        assert strict_schema_errors(candidate, compact) == strict_schema_errors(candidate, inline)
        assert Draft202012Validator(compact).is_valid(candidate) == expected
        assert Draft202012Validator(inline).is_valid(candidate) == expected
