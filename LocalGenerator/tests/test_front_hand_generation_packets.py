"""Physical contact facts survive real stage packets and provider HTTP serialization."""
import json
from copy import deepcopy

import infini_local.pipelines.transport.http as transport_http
import infini_local.pipelines.visual.contract as visual_contract
import infini_local.pipelines.visual.stage as visual_stage
import pytest
from infini_local.core import llm_config
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.author import request as author
from infini_local.pipelines.transport import admission
from infini_local.pipelines.transport import provider_wire as llm_provider_wire
from prompt_packet_helpers import request_dossier
from repair_test_helpers import provider_roundtrip, repair_with_response
from test_composable_motion_primitives import add
from test_front_hand_movement import entity, fixture
from test_low_level_three_stage_pipeline import _visual_kit, wire_transport


def _http_packet(monkeypatch, request):
    """Run production JSON encoding; intercept only the outbound socket boundary."""
    captured = []

    class Captured(BaseException):
        pass

    def intercept(req, **kwargs):
        captured.append(req.data)
        raise Captured()

    with monkeypatch.context() as patch:
        patch.setattr(transport_http, "urlopen_no_redirect", intercept)
        patch.setattr(admission, "_reserve_remote_rate_slot", lambda *a, **kw: None)
        with pytest.raises(Captured):
            transport_http.http_json("https://offline.invalid/v1/chat/completions",
                                    llm_provider_wire._clean_llm_payload(request))
    assert len(captured) == 1
    return json.loads(captured[0])


def _displaced_source(anchor):
    source, pose = fixture(axisOffsetBlocks=.5)
    source.pop("concept")
    source.pop("realization")
    source["runtimeProgram"]["calls"].remove(pose)
    attachment = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "attach")
    attachment["params"].update(anchor=anchor, reachCurve={"duration": 1 / 3, "startOffsetBlocks": 0,
        "peakOffsetBlocks": 2, "endOffsetBlocks": 0, "peakProgress": .4})
    add(source, "beam_geometry", {"length": 4, "widthBlocks": .625, "raycastTiles": True})
    return source


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("anchor", ["owner_mounted", "front_hand"])
def test_author_and_scoped_repair_deliver_physical_facts_without_reauthoring(monkeypatch, mode, anchor):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    source = _displaced_source(anchor)
    before = deepcopy(source)
    initial, _, _ = author.build_initial_author_request({}, {}, "physical-facts", model_name="offline")
    restored = provider_roundtrip(source, initial["response_format"])
    baseline = compile_runtime_program(restored)
    assert validate_runtime_program(restored)["ok"]
    assert validate_runtime_wire(baseline)["ok"]
    assert entity(baseline)["attachment"] == {"anchor": anchor, "axisOffsetPx": 8, "normalOffsetPx": 0}
    assert entity(baseline)["reach"]["peakOffsetPx"] == 32
    assert "armPose" not in entity(baseline)
    stripped = deepcopy(baseline)
    stripped.pop("runtimeContract")
    assert validate_runtime_wire(stripped)["ok"]

    broken = deepcopy(source)
    attachment = next(c for c in broken["runtimeProgram"]["calls"] if c["fn"] == "attach")
    attachment["params"]["normalOffsetBlocks"] = None
    correction = deepcopy(next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "attach"))
    correction["params"].update(anchor="owner_center", axisOffsetBlocks=0)  # frozen hostile edits
    repaired, repair_request = repair_with_response(monkeypatch, broken,
        {"callsUpsert": [correction], "note": "only the invalid normal offset"}, mode)
    assert compile_runtime_program(repaired)["runtimeProgram"] == baseline["runtimeProgram"]
    assert source == before

    initial_packet, repair_packet = [_http_packet(monkeypatch, req) for req in (initial, repair_request)]
    repair = request_dossier(repair_packet, declaration=repair_request)
    assert repair["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": attachment["id"], "paths": ["params.normalOffsetBlocks"]}]
    for packet in (initial_packet, repair_packet):
        assert packet["response_format"]["type"] == mode
        if mode == "json_schema":
            assert '"description": "' not in json.dumps(packet["response_format"]["json_schema"]["schema"])
        # These facts must be in messages, not stripped JSON Schema annotations.
        prose = " ".join(m["content"] for m in packet["messages"])
        for fact in ("MountedCenter", "front_arm_pose", "reachCurve", "4 to 10px",
                     "no automatic arm", "selected PNG", "beam", "Visual", "constant contact",
                     "compensates attachment offsets only", "hilt region", "native held-projectile pass"):
            assert fact in prose, fact
    cards = request_dossier(initial_packet, declaration=initial)["runtimeCapabilityContract"]["catalog"]["capabilities"]
    attach = next(c for c in cards if c["fn"] == "attach")
    repair_attach = next(c for c in repair["existingBrokenCapabilityCards"] if c["fn"] == "attach")
    for field in ("meaning", "enum", "type"):
        assert attach["params"]["anchor"][field] == repair_attach["params"]["anchor"][field]
    assert "MountedCenter" in json.dumps(attach)
    assert "does not cancel" in json.dumps(attach)
    assert "body center" in json.dumps(attach["params"]["reachCurve"])
    assert "not a hand anchor" in json.dumps(next(c for c in cards if c["fn"] == "beam_geometry"))


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("composition", ["mounted-path", "displaced-hand-png", "rigid-hand-png"])
def test_visual_and_repair_do_not_promise_contact_for_every_grip(wire_transport, monkeypatch, mode, composition):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    if composition == "rigid-hand-png":
        source, _ = fixture(axisOffsetBlocks=0)
    else:
        source = _displaced_source("owner_mounted" if composition == "mounted-path" else "front_hand")
        next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "beam_geometry")["params"]["startOffsetBlocks"] = -2
    accepted = compile_runtime_program(source)
    frozen = deepcopy(accepted)
    raw = _visual_kit(accepted)
    raw["item"]["grip"] = {"normalizedX": .125, "normalizedY": .5}
    if composition == "mounted-path":
        raw["entities"][1].update(assetMode="no_asset", visualProjectRef="none")
    broken = deepcopy(raw)
    broken["item"]["renderSizePx"] = 0
    responses, requests = wire_transport
    responses.extend([broken, {"schema": visual_contract.VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": {"renderSizePx": raw["item"]["renderSizePx"], "grip": {"normalizedX": .9, "normalizedY": .9}},
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [], "note": "size only"}])
    projected = visual_stage.apply_visual_director(accepted, {}, {})
    assert len(requests) == 2 and not responses
    assert projected["visualKit"] == raw
    assert {k: v for k, v in accepted.items() if k != "debug"} == frozen
    expected = deepcopy(frozen["runtimeProgram"])
    delivered = deepcopy(projected["runtimeProgram"])
    for runtime in (expected, delivered):
        for row in runtime["entities"]:
            row.pop("visual", None)
    assert delivered == expected
    for request, key in zip(requests, ("runtimeEntities", "runtimeEntitiesReadOnly")):
        http = _http_packet(monkeypatch, request)
        assert http["response_format"]["type"] == mode
        packet = request_dossier(http, declaration=request)
        row = next(row for row in packet[key] if row["id"] == "witness_entity")
        actual = entity(frozen)
        for field in ("attachment", "reach", "armPose", "beamGeometry"):
            assert (field in row) is (field in actual)
            if field in actual:
                assert row[field] == actual[field]
        guidance = packet["spritePresentationReadOnly"]
        if key == "runtimeEntities" or composition != "mounted-path":
            contact = guidance["handContactGeometry"]
            assert "the grip remains the hand-contact point" not in contact
            for fact in ("front_hand", "offset", "reach", "selected PNG", "no_asset", "body center"):
                assert fact in contact, fact
            assert "compensates attachment offsets only, not reach" in contact
            for fact in ("startOffsetPx", "MotionAxis", "end=start+axis*lengthPx", "hilt region", "native held-projectile pass"):
                assert fact in contact, fact
            if composition != "rigid-hand-png":
                assert row["beamGeometry"]["startOffsetPx"] == -32
            assert "cannot" in contact
        if key == "runtimeEntitiesReadOnly":
            assert packet["repairScope"]["fieldPermissions"]["itemPaths"] == ["renderSizePx"]
