"""Source-preserving units at the actual offline serialized stage boundaries."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import socket

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines import llm_transport
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from tests.test_low_level_three_stage_pipeline import _accepted_visual_data, _vfx_output


class _CapturedRequest(BaseException):
    """Stop after the real builder, without parsing a fabricated model answer."""


@pytest.fixture(params=["json_object", "json_schema"])
def offline_packets(monkeypatch, request):
    def denied(*args, **kwargs):
        raise AssertionError("offline packet test forbids network")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", request.param)
    monkeypatch.setattr(author, "USE_LLM", True)
    captured = []

    def stop(payload, **kwargs):
        captured.append(copy.deepcopy(payload))
        raise _CapturedRequest()

    for module in (author, visual):
        monkeypatch.setattr(module, "resolve_llm_model", lambda: "offline-test-model")
        monkeypatch.setattr(module, "trace_stage_request", lambda *a, **k: None)
        monkeypatch.setattr(module, "llm_chat_json", stop)
    yield captured, request.param
    assert captured
    assert all(row["response_format"]["type"] == request.param for row in captured)
    if directory := os.environ.get("INFINI_UNITS_PACKET_EVIDENCE_DIR"):
        path = Path(directory) / (request.node.name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scope": "synthetic offline production requests; no model response", "requests": captured}, ensure_ascii=False, indent=2) + "\n")


def _source_packets(parent, captured):
    request, _, _ = author.build_initial_author_request(parent, {}, {}, {}, "source-fact-units", model_name="offline-test-model")
    captured.append(request)
    broken = build_runtime_fixture("workbench_blade")
    next(call for call in broken["runtimeProgram"]["calls"] if call["fn"] == "set_projectile_lifetime")["params"]["lifetimeTicks"] = 0
    report = validate_runtime_program(broken)
    assert not report["ok"]
    with pytest.raises(_CapturedRequest):
        author.repair_author_item_after_failure(broken, parent, {}, {}, {}, "source-fact-units", failure_report=report)
    data = _accepted_visual_data("workbench_blade")
    for repair in (False, True):
        with pytest.raises(_CapturedRequest):
            visual._request_visual_kit(data, parent, {}, {}, {}, **({"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}))
    a, r, vd, vr = [json.loads(row["messages"][1]["content"]) for row in captured]
    return [a["parents"]["A"]["packet"]["raw"], r["parents"]["a"]["packet"]["raw"],
            vd["parents"]["parentA"]["packet"]["raw"], vr["parentFactsReadOnly"]["parentA"]["packet"]["raw"]]


@pytest.mark.parametrize("direct_extra,effective_extra,dedupe", [
    ({"itemShootSpeed": 7.125, "localNPCHitCooldown": 10, "maxPenetrate": 1, "minionSlots": 0.0, "alpha": 0},
     {"itemShootSpeed": 9.875, "localNPCHitCooldown": 20, "maxPenetrate": 3, "minionSlots": 0.5, "alpha": 128}, False),
    ({}, {"alpha": 0}, False),
    ({"alpha": 0}, {"alpha": False}, False),
    ({"alpha": 0}, {"alpha": 0.0}, False),
    ({"setsRaw": {"nested": {"source": "left", "count": 0}}}, {"setsRaw": {"nested": {"source": "right", "count": 0}}}, False),
    ({"motionReference": {"source": "literal", "extra": None}}, {"motionReference": {"source": "literal"}}, False),
    ({"alpha": 0, "source": "direct dump", "setsRaw": {"x": 0, "y": False}},
     {"source": "effective dump", "setsRaw": {"y": False, "x": 0}, "alpha": 0}, True),
], ids=["audit-numeric-loss", "missing-vs-zero", "int-vs-bool-zero", "int-vs-float-zero", "nested-source-is-fact", "nested-null-vs-absence", "provenance-only-equivalent"])
def test_sameas_preserves_all_retained_facts_in_actual_packets(offline_packets, direct_extra, effective_extra, dedupe):
    captured, _ = offline_packets
    base = {"type": 1, "internalName": "literal", "sourceMod": "Terraria", "width": 10, "height": 10}
    direct, effective = {**base, **direct_extra}, {**base, **effective_extra}
    parent = {"name": "literal source", "directProjectileRaw": direct, "effectiveProjectileRaw": effective}
    before = json.dumps(parent, sort_keys=True)
    packets = _source_packets(parent, captured)
    for raw in packets:
        assert json.dumps(raw["directProjectile"], sort_keys=True) == json.dumps(direct, sort_keys=True)
        expected = {"sameAs": "raw.directProjectile", "source": effective["source"]} if dedupe else effective
        assert json.dumps(raw["effectiveProjectile"], sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert json.dumps(parent, sort_keys=True) == before


def _vfx_packets(data, captured):
    start = len(captured)
    packet = vfx._prompt_packet(data, None, None)
    for repair in (False, True):
        with pytest.raises(_CapturedRequest):
            vfx._request(author.call_llm_vfx_director, packet, **({"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}))
    return [json.loads(row["messages"][1]["content"]) for row in captured[start:]]


@pytest.mark.parametrize("author_field,wire_field,value", [
    ("useTimeTicks", "useTime", 47), ("useAnimationTicks", "useAnimation", 53), ("scale", "itemScale", 2.75),
])
def test_vfx_actual_packets_keep_independent_accepted_cadence_and_scale(offline_packets, author_field, wire_field, value):
    captured, _ = offline_packets
    left = build_runtime_fixture("workbench_blade")
    right = copy.deepcopy(left)
    next(call for call in right["runtimeProgram"]["calls"] if call["fn"] == "configure_item_stats")["params"][author_field] = value
    assert validate_runtime_program(left)["ok"] and validate_runtime_program(right)["ok"]
    data = [compile_runtime_program(source) for source in (left, right)]
    kit = _accepted_visual_data("workbench_blade")["visualKit"]
    data = [visual._apply_kit(source, kit) for source in data]
    assert data[0]["runtimeProgram"] == data[1]["runtimeProgram"]
    assert data[0]["gameplay"][wire_field] != data[1]["gameplay"][wire_field] == value
    before = json.dumps(data, sort_keys=True)
    packets = [_vfx_packets(source, captured) for source in data]
    for index in (0, 1):
        first, second = (pair[index] for pair in packets)
        assert first != second, "accepted gameplay must change actual serialized VFX context"
        assert json.dumps(first["acceptedGameplayReadOnly"], sort_keys=True) == json.dumps(data[0]["gameplay"], sort_keys=True)
        assert json.dumps(second["acceptedGameplayReadOnly"], sort_keys=True) == json.dumps(data[1]["gameplay"], sort_keys=True)
        assert {k: v for k, v in first.items() if k != "acceptedGameplayReadOnly"} == {k: v for k, v in second.items() if k != "acceptedGameplayReadOnly"}
        assert "gameplay" not in first["outputSchema"]["properties"]
        if index:
            assert first["repairScope"] == second["repairScope"] == {}
        a, b = captured[index], captured[index + 2]
        prefix = a["_infini_prompt_cache"]["prefixChars"]
        assert prefix == b["_infini_prompt_cache"]["prefixChars"]
        assert a["messages"][1]["content"][:prefix] == b["messages"][1]["content"][:prefix]
    assert json.dumps(data, sort_keys=True) == before


@pytest.mark.parametrize("source", [{}, {"gameplay": {}}, {"gameplay": {"useTime": 0, "useAnimation": False, "itemScale": 0.0, "generatedBuff": {"enabled": False, "durationTicks": None}}}], ids=["absent", "empty", "typed-sparse-not-defaulted"])
def test_vfx_gameplay_projection_never_invents_missing_state(offline_packets, source):
    captured, _ = offline_packets
    before = json.dumps(source, sort_keys=True)
    for packet in _vfx_packets(source, captured):
        assert ("acceptedGameplayReadOnly" in packet) == ("gameplay" in source)
        if "gameplay" in source:
            assert json.dumps(packet["acceptedGameplayReadOnly"], sort_keys=True) == json.dumps(source["gameplay"], sort_keys=True)
    detached = vfx._prompt_packet(source, None, None)
    if source.get("gameplay"):
        detached["acceptedGameplayReadOnly"]["generatedBuff"]["enabled"] = "hostile detached mutation"
    assert json.dumps(source, sort_keys=True) == before


def test_actual_vfx_scale_descriptions_separate_frame_legacy_impact_and_material_units(offline_packets):
    captured, _ = offline_packets
    packets = _vfx_packets(_accepted_visual_data("workbench_blade"), captured)
    descriptions = []
    for packet, key in zip(packets, ("slots", "slotsUpsert")):
        scale = packet["outputSchema"]["properties"][key]["items"]["properties"]["scale"]
        assert {k: v for k, v in scale.items() if k != "description"} == {"type": "number", "minimum": 0.15, "maximum": 5.0}
        descriptions.append(scale["description"])
    assert descriptions[0] == descriptions[1]
    for clause in (
        "R=selected renderSizePx", "q_selected=R/max(actual final PNG frame width, height)",
        "not canvas, alpha-bbox or hitbox", "reuse_item_icon selects root item R",
        "P=projectile.scale", "initial P=D*E", "not another E or gameplay.itemScale",
        "declared R: clamp(P,0.1,8)*scale*q_selected", "absent R: max(0.05,P*scale)",
        "Projectile event body copy: clamp(P,0.1,8)*scale*q_selected",
        "Directional item body stamp: clamp(scale,0.05,8)*q_selected",
        "Dedicated impactSprite: clamp(scale,0.05,8), no main-PNG conversion",
        "spriteElement/texturedPath use explicit world-pixel dimensions/profiles, not q_selected",
    ):
        assert clause in descriptions[0], clause


def test_new_gameplay_context_does_not_widen_actual_vfx_repair_permissions(monkeypatch, offline_packets):
    captured, _ = offline_packets
    data = _accepted_visual_data("workbench_blade")
    before = copy.deepcopy(data)
    accepted = _vfx_output(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["alpha"] = 2.0
    candidate = {**accepted["slots"][0], "scale": 4.75}
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "alpha only, hostile valid scale rewrite"}
    responses = iter([raw, patch])

    def respond(request, **kwargs):
        captured.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(next(responses))}}]}

    monkeypatch.setattr(author, "llm_chat_json", respond)
    final = vfx.attach_hybrid_vfx_manifest(data, "units-frozen-repair", llm_director=author.call_llm_vfx_director)
    assert len(captured) == 2
    director, repair = [json.loads(row["messages"][1]["content"]) for row in captured]
    assert director["acceptedGameplayReadOnly"] == repair["acceptedGameplayReadOnly"] == before["gameplay"]
    assert repair["repairScope"]["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": accepted["slots"][0]["id"], "paths": ["alpha"]}], "assets": []}
    assert not repair["repairScope"]["allowCreateSlots"]
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert final["vfxManifest"] == vfx._compile_manifest(before, accepted, "units-frozen-repair")
    assert final["gameplay"] == before["gameplay"]
    assert final["runtimeProgram"] == before["runtimeProgram"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert raw["slots"][0]["alpha"] == 2.0 and candidate["scale"] == 4.75
