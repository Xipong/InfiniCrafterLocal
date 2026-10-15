"""Offline literal grammar and native serialization witnesses for Director caches."""
import copy
import json

import pytest

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


def _packet(monkeypatch, stage, fixture, mode, *, captured=None):
    from test_craft_instruction_segments import stage_packets
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    import vfx_material_fixtures
    data = (vfx_material_fixtures._data("channel_beam") if fixture == "channel_beam"
            else compile_runtime_program(build_runtime_fixture(fixture)))
    with monkeypatch.context() as mp:
        mp.setattr(vfx_material_fixtures, "_data", lambda: copy.deepcopy(data))
        if captured is not None:
            from infini_local.pipelines import vfx_generation_pipeline as sender, visual_generation_pipeline as visual
            def record(payload, schema_key, paths):
                captured.append(copy.deepcopy(payload))
                return with_schema_instruction_definitions(payload, schema_key, paths)
            mp.setattr(visual, "with_schema_instruction_definitions", record)
            mp.setattr(sender, "with_schema_instruction_definitions", record)
        return stage_packets(mp, stage, format_mode=mode, labels=("novel-a",))[0], data


@pytest.mark.parametrize("stage", ["visual", "visual_repair"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_visual_caches_literal_entity_grammar_not_roster(monkeypatch, stage, mode):
    from prompt_packet_helpers import request_dossier
    from infini_local.pipelines import visual_generation_pipeline as visual
    packets = []
    for fixture in ("workbench_blade", "door_on_chain", "channel_beam"):
        packet, data = _packet(monkeypatch, stage, fixture, mode)
        static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
        key = "entitiesUpsert" if stage.endswith("repair") else "entities"
        union = "anyOf" if mode == "json_schema" else "oneOf"
        branches = dynamic["responseSchema"]["properties"][key]["items"][union]
        for branch in branches:
            assert branch["properties"]["scale"] == {"$ref": "#/$defs/entityScale"}
        for field in ("prompt", "silhouette", "visualIdentity"):
            assert field not in branches[0]["properties"]
            assert branches[1]["properties"][field] == {"$ref": "#/$defs/entity_" + field}
        assert dynamic["responseSchema"]["properties"]["animationPlan"] == {"$ref": "#/$defs/animationPlan"}
        ids = [row["id"] for row in data["runtimeProgram"]["entities"]]
        canonical = (visual._visual_repair_schema if stage.endswith("repair") else visual._response_schema)(ids, False, data["runtimeProgram"]["itemEntityId"])
        if mode == "json_schema":
            canonical = visual._provider_strict_projection(canonical)
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
    from infini_local.pipelines import visual_generation_pipeline as visual
    from test_stable_schema_data import capture_wire
    import vfx_material_fixtures

    data = compile_runtime_program(build_runtime_fixture("equipment_tool_combat") if overlay else build_capability_witness("configure_tool"))
    before = copy.deepcopy(data)
    assert len(data["runtimeProgram"]["entities"]) == 1
    monkeypatch.setattr(vfx_material_fixtures, "_data", lambda: copy.deepcopy(data))
    packet, = stage_packets(monkeypatch, stage, format_mode=mode, labels=("novel-a",))
    ids = [data["runtimeProgram"]["itemEntityId"]]
    canonical = (visual._visual_repair_schema if stage.endswith("repair") else visual._response_schema)(ids, overlay, ids[0])
    if mode == "json_schema":
        canonical = visual._provider_strict_projection(canonical)
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
    from infini_local.core import vfx_manifest as vfx
    packets = []
    for fixture in ("workbench_blade", "door_on_chain", "channel_beam"):
        packet, data = _packet(monkeypatch, stage, fixture, mode)
        static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
        repair = stage.endswith("repair")
        key = "slotsUpsert" if repair else "slots"
        schema = dynamic["outputSchema"]
        slot = schema["properties"][key]["items"]
        assert slot["properties"]["rendererKind"] == {"$ref": "#/$defs/slot_rendererKind"}
        assert schema["properties"]["assetsUpsert" if repair else "assets"]["items"] == {"$ref": "#/$defs/asset"}
        for field in ("element", "path", "screenShake", "particle", "sound"):
            assert slot["properties"][field] == {"$ref": "#/$defs/" + field}
        for index, renderer in enumerate(vfx._RENDERER_REQUIREMENTS):
            assert slot["allOf"][index] == {"$ref": "#/$defs/rendererRule_" + renderer}
        canonical = (vfx._vfx_repair_schema if repair else vfx._director_schema)(data)
        assert request_dossier(packet)["outputSchema"] == canonical
        if mode == "json_schema":
            assert packet["response_format"]["json_schema"]["schema"] == canonical
        original_slot = canonical["properties"][key]["items"]
        for field in ("entityId", "event"):
            assert slot["properties"][field] == original_slot["properties"][field]
        assert slot["allOf"][len(vfx._RENDERER_REQUIREMENTS):] == original_slot["allOf"][len(vfx._RENDERER_REQUIREMENTS):]
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
    for fixture in ("workbench_blade", "door_on_chain", "channel_beam"):
        captured = []
        packet, _ = _packet(monkeypatch, stage, fixture, mode, captured=captured)
        before = copy.deepcopy(packet)
        assert request_dossier(packet) == request_dossier(captured[0])
        assert json.dumps(request_dossier(packet), ensure_ascii=False, separators=(",", ":")) == json.dumps(
            request_dossier(captured[0]), ensure_ascii=False, separators=(",", ":"),
        )
        original_static = json.loads(captured[0]["messages"][1]["content"])
        static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
        assert static["rules"][:-1] == original_static["rules"]
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

@pytest.mark.parametrize("stage,mode", [
    pytest.param("visual", "json_schema", id="visual-nullable-schema"),
    pytest.param("visual_repair", "json_object", id="visual-repair-json"),
    pytest.param("vfx", "off", id="vfx-unformatted"),
    pytest.param("vfx_repair", "json_schema", id="vfx-repair-schema"),
])
def test_reference_schema_reconstructs_owner_admission_and_refusal(monkeypatch, stage, mode):
    from jsonschema import Draft202012Validator
    from infini_local.core.schema_validation import strict_schema_errors
    from infini_local.core import vfx_manifest as vfx
    from infini_local.pipelines import visual_generation_pipeline as visual
    from test_visual_presentation_metadata import _visual_kit
    from test_codex_subscription_contract import _encode_nullable_fixture
    from vfx_material_fixtures import _sprite
    from prompt_packet_helpers import request_dossier
    packet, data = _packet(monkeypatch, stage, "workbench_blade", mode)
    static, dynamic = [json.loads(row["content"]) for row in packet["messages"][1:]]
    visual_stage = stage.startswith("visual")
    repair = stage.endswith("repair")
    key = "responseSchema" if visual_stage else "outputSchema"
    compact = {**dynamic[key], "$defs": static["schemaDefinitions"]["$defs"]}
    inline = request_dossier(packet)[key]
    if mode == "json_schema":
        assert inline == packet["response_format"]["json_schema"]["schema"]
    if visual_stage:
        valid = ({"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": {"inventoryScale": 1.0},
                  "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
                  "animationPlan": None, "note": "one leaf"} if repair else _visual_kit(data))
        if mode == "json_schema":
            ids = [e["id"] for e in data["runtimeProgram"]["entities"]]
            local = visual._response_schema(ids, False, data["runtimeProgram"]["itemEntityId"])
            valid = _encode_nullable_fixture(valid, local)
        invalid = copy.deepcopy(valid)
        invalid["itemPatch" if repair else "item"]["inventoryScale"] = True
        unknown = copy.deepcopy(valid)
        if repair:
            unknown["entityIdsDelete"] = ["not_in_roster"]
        else:
            unknown["entities"][0]["entityId"] = "not_in_roster"
    else:
        valid = _sprite(data)
        if repair:
            valid = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "one leaf", "slotsUpsert": valid["slots"]}
        slot_key = "slotsUpsert" if repair else "slots"
        invalid = copy.deepcopy(valid)
        invalid[slot_key][0]["element"]["count"] = True
        unknown = copy.deepcopy(valid)
        unknown[slot_key][0]["event"] = "not_in_runtime_events"
    Draft202012Validator.check_schema(compact)
    for candidate, expected in ((valid, True), (invalid, False), (unknown, False), ({}, False), (None, False)):
        assert strict_schema_errors(candidate, compact) == strict_schema_errors(candidate, inline)
        assert Draft202012Validator(compact).is_valid(candidate) == expected
        assert Draft202012Validator(inline).is_valid(candidate) == expected
