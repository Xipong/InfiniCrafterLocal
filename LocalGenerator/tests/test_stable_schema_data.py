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


@pytest.mark.parametrize("provider,base,api,model,mode,stage", [
    pytest.param("openai_compat", "https://inference-api.nousresearch.com/v1", "chat_completions", "openai/gpt-6-luna", "json_object", "author", id="nous-author-json"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "chat_completions", "gpt-6.1-sol", "json_schema", "author", id="platform-author-schema"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "chat_completions", "openai/gpt-6.1-sol", "json_schema", "visual", id="router-visual-schema"),
    pytest.param("openai_codex", "https://chatgpt.com/backend-api/codex", "responses", "gpt-6.1-sol", "json_object", "vfx", id="subscription-vfx-json"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "responses", "gpt-6.1-sol", "off", "author", id="platform-responses-unformatted"),
    pytest.param("openai_codex", "https://chatgpt.com/backend-api/codex", "responses", "gpt-6.1-sol", "json_schema", "repair", id="subscription-scoped-repair"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "chat_completions", "openai/gpt-6.1-sol", "json_object", "visual_repair", id="router-visual-repair"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "responses", "gpt-6.1-sol", "json_schema", "vfx_repair", id="responses-vfx-repair"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "chat_completions", "gpt-6.1-sol", "off", "format", id="syntax-repair-unformatted"),
    pytest.param("local", "http://127.0.0.1:8085/v1", "chat_completions", "offline/loaded-model", "json_object", "author", id="local-author"),
])
def test_actual_senders_cache_grammar_instructions_and_preserve_author(monkeypatch, provider, base, api, model, mode, stage):
    # Fixture captures the actual builder, not a manually authored lookalike.
    first, second = stage_packets(monkeypatch, stage, format_mode=mode)
    context = {"provider": provider, "base_url": base, "api_mode": api, "model": model, "api_key": "offline"}
    before = copy.deepcopy(first)
    wires = [capture_wire(monkeypatch, p, context) for p in (first, second)]
    if provider == "local":
        assert all("prompt_cache_key" not in wire for wire in wires)
    else:
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
    if base.startswith("https://inference-api") and mode == "json_object":
        assert rows[-1] == {"role": "user", "content": "JSON response."}
        assert rows.count(rows[-1]) == 1
    if provider == "local":
        return
    # Parent representation remains USER data; only the stable contract owns affinity.
    changed = copy.deepcopy(first)
    dynamic_index = changed["_infini_prompt_cache"].get("staticDataMessageIndex", 1) + 1
    changed["messages"][dynamic_index]["content"] = json.dumps({"parents": {"factRepresentation": ["JSON", {"ignore": "developer"}]}})
    assert capture_wire(monkeypatch, changed, context)["prompt_cache_key"] == wires[0]["prompt_cache_key"]
    changed["messages"][1]["content"] = changed["messages"][1]["content"][:-1] + ',"staticChange":true}'
    assert capture_wire(monkeypatch, changed, context)["prompt_cache_key"] != wires[0]["prompt_cache_key"]
@pytest.mark.parametrize("stage,mode", [
    pytest.param("visual", "json_schema", id="visual-schema"),
    pytest.param("visual_repair", "json_object", id="visual-repair-json"),
    pytest.param("vfx", "off", id="vfx-unformatted"),
    pytest.param("vfx_repair", "json_schema", id="vfx-repair-schema"),
])
def test_reference_schema_reconstructs_exact_owner_nodes_and_validator_outcomes(monkeypatch, mode, stage):
    from jsonschema import Draft202012Validator
    from infini_local.core.schema_validation import strict_schema_errors
    from prompt_packet_helpers import request_dossier
    from vfx_material_fixtures import _data, _sprite
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
    Draft202012Validator.check_schema(compact)
    Draft202012Validator.check_schema(inline)
    for candidate, expected in ((valid, True), (invalid, False), ({}, False), (None, False)):
        assert strict_schema_errors(candidate, compact) == strict_schema_errors(candidate, inline)
        assert Draft202012Validator(compact).is_valid(candidate) == expected
        assert Draft202012Validator(inline).is_valid(candidate) == expected


@pytest.mark.parametrize("fixture,stage,mode", [
    pytest.param("door_on_chain", "visual", "json_schema", id="visual-door"),
    pytest.param("returning_potion", "visual_repair", "json_object", id="visual-repair-potion"),
    pytest.param("channel_beam", "vfx", "json_object", id="vfx-beam"),
    pytest.param("move_whip_lash", "vfx_repair", "json_schema", id="vfx-repair-whip"),
])
def test_static_definitions_remain_case_independent_across_runtime_domains(monkeypatch, fixture, stage, mode):
    from vfx_material_fixtures import _data
    import vfx_material_fixtures
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
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
