"""Model spelling is lossless; canonical material wire and clocks remain unchanged."""
import copy

import pytest

from infini_local.core.vfx_material_contract import (
    element_schema, path_schema, screen_shake_schema,
    vfx_model_context, vfx_model_payload, vfx_model_schema,
)


def test_material_aliases_keep_bounds_units_and_canonical_wire():
    native = element_schema()
    model = vfx_model_schema({"properties": {"element": native}}, context="slot")["properties"]["element"]
    assert "speedMinPxPerTick" in native["properties"]
    assert "speedMinPxPerTick" not in model["properties"]
    assert model["properties"]["speedMin"] == native["properties"]["speedMinPxPerTick"]
    assert model["properties"]["coneAngle"] == native["properties"]["spreadRadians"]
    assert model["properties"]["accelY"]["minimum"] == -2
    assert "world tick squared" in model["properties"]["accelY"]["description"]
    assert "rotationSpeed" in model["required"]
    path = vfx_model_schema({"properties": {"path": path_schema()}}, context="slot")["properties"]["path"]
    assert "skip true gaps" in path["properties"]["maxGap"]["description"]
    shake = vfx_model_schema({"properties": {"screenShake": screen_shake_schema()}}, context="slot")["properties"]["screenShake"]
    assert "dissipationPerCameraVisit" in shake["required"]
    assert "ModifyScreenPosition" in shake["properties"]["dissipationPerCameraVisit"]["description"]


def test_only_material_members_change_not_literals_gameplay_or_future_fields():
    value = {"slots": [{"id": "speedMinPxPerTick", "spritePrompt": "rotationRadians",
                         "element": {"speedMinPxPerTick": 1.25, "rotationRadians": -0.5,
                                     "future": {"widthPx": 100}},
                         "path": {"rotationRadians": 7, "maxSegmentLengthPx": 20}}],
             "assets": [{"prompt": "widthPx", "id": "rotationRadians"}]}
    before = copy.deepcopy(value)
    model = vfx_model_payload(value)
    assert model["slots"][0]["element"]["speedMin"] == 1.25
    assert model["slots"][0]["element"]["future"] == {"widthPx": 100}
    assert model["slots"][0]["path"] == {"rotationRadians": 7, "maxGap": 20}
    assert model["slots"][0]["spritePrompt"] == "rotationRadians"
    assert model["assets"] == value["assets"]
    assert vfx_model_payload(model, to_wire=True) == before == value


def test_alias_collision_fails_without_overwriting():
    with pytest.raises(ValueError, match="persisted-wire spelling"):
        vfx_model_payload({"slots": [{"element": {"speedMin": 1, "speedMinPxPerTick": 2}}]}, to_wire=True)


def test_repair_context_paths_fragments_and_frozen_schema_share_spelling():
    slot = {"id": "rotationRadians", "element": {"speedMinPxPerTick": 2, "widthPx": 12}}
    packet = {"brokenFragments": {"slots": [slot]}, "validGeneratedContext": {"slots": []},
              "acceptedRuntimeProgramReadOnly": {"rotationRadians": 7},
              "parentFactsReadOnly": {"speedMinPxPerTick": 9},
              "malformedRawText": '{"rotationRadians":3}',
              "repairScope": {"fieldPermissions": {"slots": [{"slotId": "rotationRadians", "paths": ["element.speedMinPxPerTick"], "deletePaths": ['element["x.y"]']}] }},
              "exactErrors": [{"path": "$.slots[0].element.speedMinPxPerTick", "message": "invalid speedMinPxPerTick"}],
              "outputSchema": {"properties": {"slotsUpsert": {"items": {"const": slot}}}}}
    before = copy.deepcopy(packet)
    model = vfx_model_context(packet)
    assert model["brokenFragments"]["slots"][0]["element"] == {"speedMin": 2, "width": 12}
    permission = model["repairScope"]["fieldPermissions"]["slots"][0]
    assert permission == {"slotId": "rotationRadians", "paths": ["element.speedMin"], "deletePaths": ['element["x.y"]']}
    assert model["exactErrors"][0]["path"] == "$.slots[0].element.speedMin"
    assert model["outputSchema"]["properties"]["slotsUpsert"]["items"]["const"] == model["brokenFragments"]["slots"][0]
    for key in ("acceptedRuntimeProgramReadOnly", "parentFactsReadOnly", "malformedRawText"):
        assert model[key] == before[key]
    assert packet == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_provider_short_response_repairs_exact_field_and_preserves_wire(monkeypatch, mode):
    import json
    from infini_local.core import vfx_manifest as vfx
    from infini_local.pipelines import vfx_generation_pipeline as stage
    from prompt_packet_helpers import request_dossier
    from vfx_material_fixtures import _data, _sprite

    data = _data()
    native = _sprite(data)
    # Hand-written model dialect, independently of the projection under test.
    material = {
        "spawn": {"shape": "point"}, "texture": {"source": "item", "assetId": "", "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}, "attachment": "world", "count": 2,
        "forwardOffset": 8.0, "sideOffset": -3.0, "speedMin": 1.0, "speedMax": 2.0,
        "coneAngle": 0.75, "inheritVelocity": 0.2, "drag": 0.95,
        "accelX": 0.0, "accelY": 0.05, "rotation": 0.0, "rotationSpeed": -0.1,
        "width": 12.0, "height": 5.0,
        **{key: copy.deepcopy(native["slots"][0]["element"][key])
           for key in ("widthProfile", "heightProfile", "opacityProfile", "colorProfile")},
    }
    initial = copy.deepcopy(native)
    initial["slots"][0]["element"] = dict(material, speedMax=25)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "speed limit only",
             "slotsUpsert": [dict(initial["slots"][0], element=material)]}
    pending, sent = iter([initial, patch]), []

    def reply(request, **_kwargs):
        sent.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(next(pending))}}]}

    monkeypatch.setattr(stage, "USE_LLM", True)
    monkeypatch.setattr(stage, "resolve_llm_model", lambda: "explicit-offline-model")
    monkeypatch.setattr(stage, "llm_chat_json", reply)
    monkeypatch.setattr(stage, "llm_json_response_format", lambda name, **kw:
                        {"type": "json_schema", "json_schema": {"name": name, "schema": kw["schema"], "strict": True}}
                        if mode == "json_schema" else {"type": "json_object"})
    result = vfx.attach_vfx_manifest(data, "short-vfx-repair", llm_director=stage.call_llm_vfx_director)
    assert result["debug"]["vfxDirectorRaw"] == native
    assert vfx.validate_vfx_manifest_wire(result)["ok"]
    assert len(sent) == 2
    initial_context, repair = map(request_dossier, sent)
    element = initial_context["outputSchema"]["properties"]["slots"]["items"]["properties"]["element"]
    assert "speedMax" in element["required"] and "speedMaxPxPerTick" not in element["properties"]
    assert repair["repairScope"]["fieldPermissions"]["slots"][0]["paths"] == ["element.speedMax"]
    assert repair["brokenFragments"]["slots"][0]["element"]["speedMax"] == 25
    assert repair["exactErrors"][0]["path"] == "$.slots[0].element.speedMax"
    repaired_element = repair["outputSchema"]["properties"]["slotsUpsert"]["items"]["properties"]["element"]
    assert repaired_element["properties"]["speedMax"]["maximum"] == 24
    assert repaired_element["properties"]["width"]["const"] == 12.0
    assert result["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == ["$.slotsUpsert[0].element.speedMaxPxPerTick"]
    if mode == "json_schema":
        assert sent[1]["response_format"]["json_schema"]["schema"] == repair["outputSchema"]


def test_fresh_provider_does_not_accept_old_wire_spelling(monkeypatch):
    from infini_local.core.vfx_manifest import MalformedVfxDirectorOutput
    from infini_local.pipelines import vfx_generation_pipeline as stage
    monkeypatch.setattr(stage, "USE_LLM", True)
    monkeypatch.setattr(stage, "resolve_llm_model", lambda: "explicit-offline-model")
    monkeypatch.setattr(stage, "llm_chat_json", lambda *_a, **_kw: {
        "choices": [{"message": {"content": '{"slots":[{"element":{"speedMinPxPerTick":1}}]}'}}]})
    from infini_local.core import vfx_manifest as vfx
    from vfx_material_fixtures import _data
    output = stage.call_llm_vfx_director("test", vfx._prompt_packet(_data(), None, None), 100, 0, 1)
    assert isinstance(output, MalformedVfxDirectorOutput)
    assert "persisted-wire spelling" in output.error


def test_schema_projection_does_not_rewrite_opaque_frozen_asset_data():
    opaque = {"element": {"widthPx": 4}, "path": {"maxSegmentLengthPx": 12}}
    schema = {"properties": {"assetsUpsert": {"items": {"properties": {
        "future": {"const": opaque, "properties": {"element": {"const": opaque["element"]}}},
    }}}}}
    assert vfx_model_schema(schema) == schema
