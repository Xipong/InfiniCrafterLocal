"""Canonical grammar is application instructions; case constraints stay USER."""
import copy
import json

import pytest

from infini_local.pipelines import llm_transport as transport
from test_craft_instruction_segments import stage_packets


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("offline schema test attempted network"))


PROVIDERS = [
    ("openai_compat", "https://inference-api.nousresearch.com/v1", "chat_completions", "openai/gpt-6-luna"),
    ("openai_compat", "https://api.openai.com/v1", "chat_completions", "gpt-6.1-sol"),
    ("openrouter", "https://openrouter.ai/api/v1", "chat_completions", "openai/gpt-6.1-sol"),
    ("openai_codex", "https://chatgpt.com/backend-api/codex", "responses", "gpt-6.1-sol"),
    ("openai_compat", "https://api.openai.com/v1", "responses", "gpt-6.1-sol"),
]


def capture_wire(monkeypatch, packet, context):
    from test_craft_instruction_segments import Captured
    from infini_local.services import codex_auth as auth
    from types import SimpleNamespace
    wires = []
    def stop(url, wire, **kwargs):
        wires.append(copy.deepcopy(wire))
        if context["provider"] == "openai_codex":
            assert kwargs["headers"]["session-id"] == wire["prompt_cache_key"]
        raise Captured()
    monkeypatch.setattr(transport, "http_json", stop)
    monkeypatch.setattr(auth, "get_credentials", lambda: SimpleNamespace(access_token="offline", account_id="offline"))
    monkeypatch.setattr(auth, "post_sse", stop)
    with pytest.raises(Captured):
        transport._llm_json_single_context(packet, 3, context)
    assert len(wires) == 1
    return wires[0]


def wire_text(row):
    content = row["content"]
    return content if isinstance(content, str) else "".join(block["text"] for block in content)


@pytest.mark.parametrize("provider,base,api,model", PROVIDERS)
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
@pytest.mark.parametrize("stage", ["author", "repair", "format", "visual", "visual_repair", "vfx", "vfx_repair"])
def test_actual_senders_cache_grammar_instructions_and_preserve_author(monkeypatch, provider, base, api, model, mode, stage):
    # Fixture captures the actual builder, not a manually authored lookalike.
    first, second = stage_packets(monkeypatch, stage, format_mode=mode)
    context = {"provider": provider, "base_url": base, "api_mode": api, "model": model, "api_key": "offline"}
    before = copy.deepcopy(first)
    wires = [capture_wire(monkeypatch, p, context) for p in (first, second)]
    assert wires[0]["prompt_cache_key"] == wires[1]["prompt_cache_key"]
    rows = wires[0].get("messages", wires[0].get("input"))
    authored = [row for row in rows if wire_text(row) != "JSON response."]
    if api == "responses":
        assert wires[0]["instructions"] == first["messages"][0]["content"]
        source = first["messages"][1:]
    else:
        source = first["messages"]
    assert [(r["role"], wire_text(r)) for r in authored] == [(r["role"], r["content"]) for r in source]
    assert first == before
    assert "_infini_prompt_cache" not in wires[0]
    if mode == "json_schema":
        format_value = wires[0].get("response_format") or wires[0]["text"]["format"]
        effective = format_value.get("json_schema", format_value)["schema"]
        assert effective == first["response_format"]["json_schema"]["schema"]
        assert '"$ref"' not in json.dumps(effective) or stage in {"author", "repair", "format"}
    if "schemaDefinitions" not in json.loads(first["messages"][1]["content"]):
        return  # Existing Author wire/key regression is tested separately.
    changed = copy.deepcopy(first)
    dynamic = json.loads(changed["messages"][2]["content"])
    schema_key = "responseSchema" if stage.startswith("visual") else "outputSchema"
    # Change the accepted entity set's exact schema constraints along with facts.
    def rename(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "entityId" and isinstance(value, dict) and "enum" in value:
                    value["enum"] = ["unseen_body"]
                else:
                    rename(value)
        elif isinstance(node, list):
            for value in node:
                rename(value)
    rename(dynamic[schema_key])
    dynamic["novelCase"] = {"entityId": "unseen_body"}
    changed["messages"][2]["content"] = json.dumps(dynamic, ensure_ascii=False, separators=(",", ":"))
    if mode == "json_schema":
        rename(changed["response_format"]["json_schema"]["schema"])
    tail_wire = capture_wire(monkeypatch, changed, context)
    assert tail_wire["prompt_cache_key"] == wires[0]["prompt_cache_key"]
    definitions = json.loads(changed["messages"][1]["content"])
    next(iter(definitions["schemaDefinitions"]["$defs"].values()))["description"] = "Canonical owner revision."
    changed["messages"][1]["content"] = json.dumps(definitions, separators=(",", ":"))
    revised = capture_wire(monkeypatch, changed, context)
    assert revised["prompt_cache_key"] != tail_wire["prompt_cache_key"]


@pytest.mark.parametrize("mutation", ["nested_duplicate", "escaped_duplicate", "nan", "infinity", "overflow_static", "overflow_dynamic", "overlap", "boolean_endpoint", "null_endpoint", "out_of_bounds", "wrongrole", "unknown_key", "missing_instruction", "not_object", "empty_defs", "schema_extra"])
def test_static_schema_declaration_refuses_malformed_objects_before_sender(monkeypatch, mutation):
    first = stage_packets(monkeypatch, "vfx")[0]
    if mutation == "nested_duplicate":
        first["messages"][1]["content"] = '{"schemaDefinitions":{"$defs":{"x":{"type":"object","type":"string"}}}}'
    elif mutation == "escaped_duplicate":
        first["messages"][2]["content"] = r'{"x":1,"\u0078":2}'
    elif mutation in {"nan", "infinity", "overflow_static", "overflow_dynamic"}:
        lexeme = "NaN" if mutation == "nan" else "Infinity" if mutation == "infinity" else "1e999"
        index = 2 if mutation == "overflow_dynamic" else 1
        first["messages"][index]["content"] = '{"schemaDefinitions":{"$defs":{"x":{"enum":[' + lexeme + ']}}}}'
    elif mutation == "overlap":
        first["messages"][2]["content"] = first["messages"][1]["content"]
    elif mutation in {"boolean_endpoint", "null_endpoint", "out_of_bounds"}:
        first["_infini_prompt_cache"]["instructionMessageIndex"] = {"boolean_endpoint": True, "null_endpoint": None, "out_of_bounds": 99}[mutation]
    elif mutation == "wrongrole":
        first["messages"][1]["role"] = "user"
    elif mutation == "unknown_key":
        first["_infini_prompt_cache"]["other"] = 2
    elif mutation == "missing_instruction":
        first["_infini_prompt_cache"] = {"staticDataMessageIndex": 2}
    elif mutation == "not_object":
        first["messages"][1]["content"] = '[]'
    elif mutation == "empty_defs":
        first["messages"][1]["content"] = '{"schemaDefinitions":{"$defs":{}}}'
    else:
        first["messages"][1]["content"] = '{"schemaDefinitions":{"$defs":{"x":{"type":"string"}},"caseFact":1}}'
    monkeypatch.setattr(transport, "http_json", lambda *a, **k: pytest.fail("malformed declaration reached HTTP"))
    with pytest.raises(ValueError):
        transport._llm_json_single_context(first, 3, {"provider": "openai_compat", "base_url": "https://api.openai.com/v1", "model": "gpt-6.1-sol"})


@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
@pytest.mark.parametrize("stage", ["visual", "visual_repair", "vfx", "vfx_repair"])
def test_reference_schema_reconstructs_exact_owner_nodes_and_validator_outcomes(monkeypatch, mode, stage):
    from jsonschema import Draft202012Validator
    from infini_local.core.schema_validation import strict_schema_errors
    from prompt_packet_helpers import request_dossier
    from vfx_material_fixtures import _data, _sprite, _path
    from test_visual_presentation_metadata import _visual_kit
    from infini_local.pipelines import visual_generation_pipeline as visual
    from infini_local.core import vfx_manifest as vfx
    first = stage_packets(monkeypatch, stage, format_mode=mode)[0]
    dynamic = json.loads(first["messages"][2]["content"])
    key = "responseSchema" if stage.startswith("visual") else "outputSchema"
    compact = copy.deepcopy(dynamic[key])
    compact["$defs"] = json.loads(first["messages"][1]["content"])["schemaDefinitions"]["$defs"]
    inline = request_dossier(first)[key]
    if mode == "json_schema":
        assert inline == first["response_format"]["json_schema"]["schema"]
    data = _data()
    if stage.startswith("visual"):
        kit = _visual_kit(data)
        valid = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"inventoryScale": 1.0}, entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="exact leaf") if stage.endswith("repair") else kit
        invalid = copy.deepcopy(valid)
        invalid["itemPatch" if stage.endswith("repair") else "item"]["inventoryScale"] = True
    else:
        valid = _sprite(data)
        invalid = copy.deepcopy(valid)
        invalid["slots"][0]["element"]["count"] = True
        if stage.endswith("repair"):
            valid = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "exact leaf", "slotsUpsert": valid["slots"]}
            invalid = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "exact leaf", "slotsUpsert": invalid["slots"]}
    # Provider nullable scaffolding is generated by the existing projection owner.
    if mode == "json_schema" and stage.startswith("visual"):
        from test_codex_subscription_contract import _encode_nullable_fixture
        local = visual._visual_repair_schema([e["id"] for e in data["runtimeProgram"]["entities"]], False, data["runtimeProgram"]["itemEntityId"]) if stage.endswith("repair") else visual._response_schema([e["id"] for e in data["runtimeProgram"]["entities"]], False, data["runtimeProgram"]["itemEntityId"])
        valid = _encode_nullable_fixture(valid, local)
        invalid = copy.deepcopy(valid)
        invalid["itemPatch" if stage.endswith("repair") else "item"]["inventoryScale"] = True
    if stage.startswith("vfx"):
        from test_vfx_material_admission_contracts import _screen_shake, _library_particle
        from test_vfx_sound_selection import _sound
        witnesses = [("element", _sprite(data), "count"), ("path", _path(data), "widthPx"),
                     ("screenShake", _screen_shake(data), "strengthPx"),
                     ("particle", _library_particle(data), "count")]
        sound = _sound(data)
        sound["slots"][0]["sound"] = {"volume": 0.5, "pitch": 0, "pitchVariance": 0}
        witnesses.append(("sound", sound, "volume"))
        for name, witness, field in witnesses:
            if stage.endswith("repair"):
                witness = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "payload witness", "slotsUpsert": witness["slots"]}
            row_key = "slotsUpsert" if stage.endswith("repair") else "slots"
            for mutation in ("valid", "boolean", "missing", "foreign", "null"):
                candidate = copy.deepcopy(witness)
                payload = candidate[row_key][0][name]
                if mutation == "boolean":
                    payload[field] = True
                elif mutation == "missing":
                    del payload[field]
                elif mutation == "foreign":
                    payload["unexpected"] = 1
                elif mutation == "null":
                    candidate[row_key][0][name] = None
                assert strict_schema_errors(candidate, compact) == strict_schema_errors(candidate, inline)
                assert Draft202012Validator(compact).is_valid(candidate) == (mutation == "valid")
                assert Draft202012Validator(inline).is_valid(candidate) == (mutation == "valid")
    Draft202012Validator.check_schema(compact)
    Draft202012Validator.check_schema(inline)
    for candidate, expected in ((valid, True), (invalid, False), ({}, False), (None, False)):
        assert strict_schema_errors(candidate, compact) == strict_schema_errors(candidate, inline)
        assert Draft202012Validator(compact).is_valid(candidate) == expected
        assert Draft202012Validator(inline).is_valid(candidate) == expected


@pytest.mark.parametrize("fixture", ["workbench_blade", "door_on_chain", "returning_potion", "channel_beam", "move_whip_lash"])
@pytest.mark.parametrize("stage", ["visual", "visual_repair", "vfx", "vfx_repair"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_static_definitions_remain_case_independent_across_runtime_domains(monkeypatch, fixture, stage, mode):
    from vfx_material_fixtures import _data
    import vfx_material_fixtures
    from infini_local.core.runtime_authoring import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    ordinary = stage_packets(monkeypatch, stage, format_mode=mode)[0]
    if fixture in {"channel_beam", "move_whip_lash"}:
        data = _data(fixture)
    else:
        data = compile_runtime_program(build_runtime_fixture(fixture))
    monkeypatch.setattr(vfx_material_fixtures, "_data", lambda: copy.deepcopy(data))
    other = stage_packets(monkeypatch, stage, format_mode=mode)[0]
    assert ordinary["messages"][:2] == other["messages"][:2]
    assert ordinary["messages"][2] != other["messages"][2] or fixture == "workbench_blade"
    # Full provider schema remains exact and inline, regardless of affinity.
    from prompt_packet_helpers import request_dossier
    schema_key = "responseSchema" if stage.startswith("visual") else "outputSchema"
    if mode == "json_schema":
        assert other["response_format"]["json_schema"]["schema"] == request_dossier(other)[schema_key]


@pytest.mark.parametrize("stage", ["visual", "visual_repair", "vfx", "vfx_repair"])
def test_schema_owner_revision_invalidates_actual_sender_affinity(monkeypatch, stage):
    from infini_local.core import vfx_manifest as vfx
    from infini_local.pipelines import visual_generation_pipeline as visual
    before = stage_packets(monkeypatch, stage)[0]
    owner, name = (visual, "_visual_item_schema") if stage.startswith("visual") else (vfx, "element_schema")
    canonical = getattr(owner, name)
    def revised():
        schema = canonical()
        schema["properties"]["prompt" if stage.startswith("visual") else "count"]["description"] = "Canonical revision witness."
        return schema
    monkeypatch.setattr(owner, name, revised)
    after = stage_packets(monkeypatch, stage)[0]
    assert before["messages"][1] != after["messages"][1]
    assert before["messages"][2] == after["messages"][2]
    context = dict(provider="openai_codex", base_url="https://chatgpt.com/backend-api/codex", api_mode="responses", model="gpt-6.1-sol")
    assert capture_wire(monkeypatch, before, context)["prompt_cache_key"] != capture_wire(monkeypatch, after, context)["prompt_cache_key"]


@pytest.mark.parametrize("stage", ["visual", "visual_repair", "vfx", "vfx_repair"])
def test_canonical_grammar_nodes_share_complete_stable_developer_contract(monkeypatch, stage):
    first, second = stage_packets(monkeypatch, stage)
    assert [row["role"] for row in first["messages"]] == ["system", "developer", "user"]
    assert first["_infini_prompt_cache"] == {"instructionMessageIndex": 1}
    assert first["messages"][:2] == second["messages"][:2]
    static = json.loads(first["messages"][1]["content"])
    dynamic = json.loads(first["messages"][2]["content"])
    assert "schemaDefinitions" in static
    assert "schemaDefinitions" not in dynamic
    assert static["rules"][-1].startswith("The output schema's #/$defs/ references resolve against DEVELOPER schemaDefinitions.$defs;")
    assert set(static["schemaDefinitions"]) == {"$defs"}
    defs = static["schemaDefinitions"]["$defs"]
    if stage.startswith("vfx"):
        assert set(defs) == {"element", "path", "screenShake", "particle", "sound"}
        schema = dynamic["outputSchema"]
        slot = schema["properties"]["slotsUpsert" if stage.endswith("repair") else "slots"]["items"]
        for key in defs:
            assert slot["properties"][key] == {"$ref": "#/$defs/" + key}
    else:
        key = "itemPatch" if stage.endswith("repair") else "item"
        assert set(defs) == {key}
        item = dynamic["responseSchema"]["properties"][key]
        assert (item["anyOf"][0] if key == "itemPatch" else item) == {"$ref": "#/$defs/" + key}
    assert not static.keys() & dynamic.keys()
    assert first["messages"][2] != second["messages"][2]
    assert transport._prompt_cache_boundary(first) == (1, len(first["messages"][1]["content"]))
