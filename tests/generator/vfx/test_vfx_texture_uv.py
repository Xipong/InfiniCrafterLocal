"""Literal UV selection, saved absence and real offline provider/Repair boundary."""
import copy
import json
import pytest
from infini_local.core import llm_config
import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.validation as vfx_validation
import infini_local.pipelines.vfx.stage as vfx_stage
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx.materials import vfx_model_payload
from infini_local.pipelines.vfx import request as stage
from tests.generator.vfx_material_fixtures import _data, _sprite, _path, _history
from prompt_packet_helpers import request_dossier


@pytest.mark.parametrize("factory,payload,turn,mirrors", [
    pytest.param(_sprite, "element", 0, 0, id="sprite-identity"),
    pytest.param(_path, "path", 0, 0, id="path-identity"),
    pytest.param(_history, "trail", 0, 0, id="history-identity"),
    pytest.param(_sprite, "element", 1, 1, id="sprite-quarter-turn-mirror-u"),
    pytest.param(_path, "path", 2, 2, id="path-half-turn-mirror-v"),
    pytest.param(_history, "trail", 3, 3, id="history-three-quarter-turn-mirror-both"),
])
def test_complete_uv_transform_roundtrips(factory,payload,turn,mirrors):
    # This boundary copies literal UV metadata; it does not execute renderer
    # geometry. Exercise each slot shape and every field value, not 3x4x4 copies.
    data=_data();raw=factory(data)
    transform={"quarterTurns":turn,"mirrorU":bool(mirrors&1),"mirrorV":bool(mirrors&2)}
    raw["slots"][0][payload]["texture"]["uv"]=transform
    assert vfx_validation.validate_vfx_director_output(raw,data)["ok"]
    data["vfxManifest"]=vfx_projection._compile_manifest(data,raw,"uv")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"]["slots"][0][payload]["texture"]["uv"]==transform


@pytest.mark.parametrize("bad", [None,{}, {"quarterTurns":1}, {"quarterTurns":4,"mirrorU":False,"mirrorV":False}, {"quarterTurns":True,"mirrorU":False,"mirrorV":False}])
def test_present_invalid_uv_is_not_identity(bad):
    data=_data();raw=_sprite(data);raw["slots"][0]["element"]["texture"]["uv"]=bad
    assert not vfx_validation.validate_vfx_director_output(raw,data)["ok"]
    data["vfxManifest"]=vfx_projection._compile_manifest(data,raw,"uv_bad")
    assert not vfx_validation.validate_vfx_manifest_wire(data)["ok"]




@pytest.mark.parametrize("mode",["json_object","json_schema"])
@pytest.mark.parametrize("repair",[False,True])
def test_actual_provider_and_repair_preserve_uv_without_nullable_transport(monkeypatch,mode,repair):
    data=_data();accepted=_sprite(data)
    accepted["slots"][0]["element"]["texture"]["uv"]={"quarterTurns":1,"mirrorU":True,"mirrorV":False}
    initial=copy.deepcopy(accepted)
    if repair:initial["slots"][0]["element"]["texture"]["uv"]["quarterTurns"]=5
    patch={"schema":vfx_contract.VFX_REPAIR_PATCH_SCHEMA,"note":"UV turn only","slotsUpsert":copy.deepcopy(accepted["slots"])}
    # Hostile valid sibling mutation must be ignored by frozen-first Repair.
    patch["slotsUpsert"][0]["element"]["texture"]["uv"]["mirrorU"]=False
    pending=iter([vfx_model_payload(initial),vfx_model_payload(patch)]);sent=[]
    def reply(request,**kwargs):
        sent.append(copy.deepcopy(request))
        return {"choices":[{"message":{"content":json.dumps(next(pending))}}]}
    monkeypatch.setattr(stage,"USE_LLM",True)
    monkeypatch.setattr(stage,"resolve_llm_model",lambda:"offline-uv-model")
    monkeypatch.setattr(stage,"llm_chat_json",reply)
    monkeypatch.setattr(llm_config,"LLM_RESPONSE_FORMAT_MODE",mode)
    result=vfx_stage.attach_vfx_manifest(data,"uv_boundary",llm_director=stage.call_llm_vfx_director)
    assert len(sent)==(2 if repair else 1)
    assert result["debug"]["vfxDirectorRaw"]==accepted
    assert vfx_validation.validate_vfx_manifest_wire(result)["ok"]
    initial_schema=request_dossier(sent[0])["outputSchema"]
    selector=initial_schema["properties"]["slots"]["items"]["properties"]["element"]["properties"]["texture"]
    assert "uv" in selector["required"]
    assert set(selector["properties"]["uv"]["required"])=={"quarterTurns","mirrorU","mirrorV"}
    assert strict_schema_errors(None,selector["properties"]["uv"])
    if mode=="json_schema":assert sent[0]["response_format"]["json_schema"]["strict"]
    if repair:
        packet=request_dossier(sent[1])
        assert packet["repairScope"]["fieldPermissions"]["slots"][0]["paths"]==["element.texture.uv.quarterTurns"]
