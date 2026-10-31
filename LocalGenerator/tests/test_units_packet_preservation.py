"""Source-preserving units at the actual offline serialized stage boundaries."""
from __future__ import annotations

from infini_local.core import llm_config
from infini_local.pipelines.vfx import request as vfx_transport
from prompt_packet_helpers import request_dossier, dossier_text

import copy
import json
import os
from pathlib import Path
import socket

import pytest

import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.validation as vfx_validation
import infini_local.pipelines.vfx.prompt as vfx_prompt
import infini_local.pipelines.vfx.stage as vfx_stage
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.author import request as author
import infini_local.pipelines.visual.request as visual_request
import infini_local.pipelines.visual.stage as visual_stage
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
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", request.param)
    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(vfx_transport, "USE_LLM", True)
    captured = []

    def stop(payload, **kwargs):
        captured.append(copy.deepcopy(payload))
        raise _CapturedRequest()

    for module in (author, visual_request, vfx_transport):
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
    request, _, _ = author.build_initial_author_request(parent, {}, "source-fact-units", model_name="offline-test-model")
    captured.append(request)
    broken = build_runtime_fixture("workbench_blade")
    next(call for call in broken["runtimeProgram"]["calls"] if call["fn"] == "projectile_lifetime")["params"]['lifetimeSeconds'] = (0) / 60
    report = validate_runtime_program(broken)
    assert not report["ok"]
    with pytest.raises(_CapturedRequest):
        author.repair_author_item_after_failure(broken, parent, {}, "source-fact-units", failure_report=report)
    data = _accepted_visual_data("workbench_blade")
    for repair in (False, True):
        with pytest.raises(_CapturedRequest):
            visual_request._request_visual_kit(data, parent, {}, **({"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}))
    a, r, vd, vr = [request_dossier(row) for row in captured]
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
    packet = vfx_prompt._prompt_packet(data, None, None)
    for repair in (False, True):
        with pytest.raises(_CapturedRequest):
            vfx_stage._request(vfx_transport.call_llm_vfx_director, packet, **({"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}))
    return [request_dossier(row) for row in captured[start:]]


@pytest.mark.parametrize("envelope", ["root", "fingerprint"])
@pytest.mark.parametrize("facts", [
    {"itemScale": 0.7, "armorPenetration": 13, "useLimitPerAnimation": 4},
    {"itemScale": 1.0, "armorPenetration": 0, "useLimitPerAnimation": None},
    {"itemScale": 0.0, "armorPenetration": 0, "useLimitPerAnimation": 0},
    {},
], ids=["native-nondefault", "native-neutral-and-unlimited", "explicit-zero", "unobserved"])
def test_native_item_stats_preserve_presence_and_nullable_use_limit_in_stage_packets(offline_packets, envelope, facts):
    captured, _ = offline_packets
    parent = {"name": "literal source", **(facts if envelope == "root" else {"fingerprint": facts})}
    # A present null explicitly owns the current observation; older fingerprint
    # data cannot turn the native no-limit value into a cap.
    if envelope == "root" and "useLimitPerAnimation" in facts and facts["useLimitPerAnimation"] is None:
        parent["fingerprint"] = {"useLimitPerAnimation": 8}
    before = copy.deepcopy(parent)
    for raw in _source_packets(parent, captured):
        item = raw["item"]
        for field in ("itemScale", "armorPenetration", "useLimitPerAnimation"):
            assert (field in item) == (field in facts)
            if field in facts:
                assert json.dumps(item[field]) == json.dumps(facts[field])
        assert all(field not in raw.get("vanillaFlags", {}) for field in facts)
    assert parent == before


@pytest.mark.parametrize("author_field,wire_field,value", [
    ("useTimeSeconds", "useTime", 47), ("useAnimationSeconds", "useAnimation", 53), ("scale", "itemScale", 2.75),
])
def test_vfx_actual_packets_keep_independent_accepted_cadence_and_scale(offline_packets, author_field, wire_field, value):
    captured, _ = offline_packets
    left = build_runtime_fixture("workbench_blade")
    right = copy.deepcopy(left)
    next(call for call in right["runtimeProgram"]["calls"] if call["fn"] == "item_stats")["params"][author_field] = value / 60 if author_field.endswith("Seconds") else value
    assert validate_runtime_program(left)["ok"] and validate_runtime_program(right)["ok"]
    data = [compile_runtime_program(source) for source in (left, right)]
    kit = _accepted_visual_data("workbench_blade")["visualKit"]
    data = [visual_stage._apply_kit(source, kit) for source in data]
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
        assert a["_infini_prompt_cache"] == b["_infini_prompt_cache"] == {"instructionMessageIndex": 1}
        assert a["messages"][1]["content"] == b["messages"][1]["content"]
    assert json.dumps(data, sort_keys=True) == before


@pytest.mark.parametrize("source", [{}, {"gameplay": {}}, {"gameplay": {"useTime": 0, "useAnimation": False, "itemScale": 0.0, "generatedBuff": {"enabled": False, "durationTicks": None}}}], ids=["absent", "empty", "typed-sparse-not-defaulted"])
def test_vfx_gameplay_projection_never_invents_missing_state(offline_packets, source):
    captured, _ = offline_packets
    before = json.dumps(source, sort_keys=True)
    for packet in _vfx_packets(source, captured):
        assert ("acceptedGameplayReadOnly" in packet) == ("gameplay" in source)
        if "gameplay" in source:
            assert json.dumps(packet["acceptedGameplayReadOnly"], sort_keys=True) == json.dumps(source["gameplay"], sort_keys=True)
    detached = vfx_prompt._prompt_packet(source, None, None)
    if source.get("gameplay"):
        detached["acceptedGameplayReadOnly"]["generatedBuff"]["enabled"] = "hostile detached mutation"
    assert json.dumps(source, sort_keys=True) == before


def test_new_gameplay_context_does_not_widen_actual_vfx_repair_permissions(monkeypatch, offline_packets):
    captured, _ = offline_packets
    data = _accepted_visual_data("workbench_blade")
    before = copy.deepcopy(data)
    accepted = _vfx_output(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["alpha"] = 2.0
    candidate = {**accepted["slots"][0], "duration": 31}
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "alpha only, hostile valid lifetime rewrite"}
    from infini_local.core.vfx.materials import vfx_model_payload
    responses = iter([vfx_model_payload(raw), vfx_model_payload(patch)])

    def respond(request, **kwargs):
        captured.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(next(responses))}}]}

    monkeypatch.setattr(author, "llm_chat_json", respond)

    monkeypatch.setattr(vfx_transport, "llm_chat_json", respond)
    final = vfx_stage.attach_vfx_manifest(data, "units-frozen-repair", llm_director=vfx_transport.call_llm_vfx_director)
    assert len(captured) == 2
    director, repair = [request_dossier(row) for row in captured]
    assert director["acceptedGameplayReadOnly"] == repair["acceptedGameplayReadOnly"] == before["gameplay"]
    assert repair["repairScope"]["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": accepted["slots"][0]["id"], "paths": ["alpha"]}], "assets": []}
    assert not repair["repairScope"]["allowCreateSlots"]
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert final["vfxManifest"] == vfx_projection._compile_manifest(before, accepted, "units-frozen-repair")
    assert final["gameplay"] == before["gameplay"]
    assert final["runtimeProgram"] == before["runtimeProgram"]
    assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]
    assert raw["slots"][0]["alpha"] == 2.0 and candidate["duration"] == 31


@pytest.mark.parametrize("mode", ["selected", "representative"])
def test_old_ammo_keys_are_not_promoted(mode):
    from infini_local.pipelines.context.parents import compact_ammo_profile, effective_projectile_profile_of
    raw = {"selectedPlayerAmmoRaw": {"type": 97}, "selectedPlayerProjectileRaw": {"type": 1}} if mode == "selected" else {
        "representativeAmmoRaw": [{"type": 97}], "representativeProjectileRaw": [{"type": 1}]}
    item = {"ammoRaw": raw}
    assert compact_ammo_profile(item) == {}
    assert effective_projectile_profile_of(item) == {}
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
    raw = raw_parent_card_for_llm(item)["raw"]
    assert "effectiveProjectile" not in raw and "directProjectile" not in raw
    assert "ammo" not in raw


def test_current_live_and_dump_ammo_packets_remain_available(monkeypatch):
    from infini_local.pipelines.context import parents
    item = {"ammoRaw": {"mode": "weapon_uses_ammo", "ammoId": 97,
        "playerInventoryAmmoRaw": [{"type": 97, "damage": 5}], "playerInventoryProjectileRaw": [{"type": 1}],
        "fallbackAmmoRaw": [{"type": 97}], "fallbackProjectileRaw": [{"type": 1}]}}
    compact = parents.compact_ammo_profile(item)
    assert compact == item["ammoRaw"]
    assert parents.effective_projectile_profile_of(item) == {}
    looked_up = []
    def lookup(projectile_id):
        looked_up.append(projectile_id)
        return {"type": 1, "tileCollide": True}
    monkeypatch.setattr(parents, "runtime_projectile_lookup", lookup)
    dump = {"useAmmo": 97}
    assert parents.compact_ammo_profile(dump) == {}
    assert parents.effective_projectile_profile_of(dump) == {} and looked_up == []
    dump["shoot"] = 1
    effective = parents.effective_projectile_profile_of(dump)
    assert effective["type"] == 1 and effective["tileCollide"] is True
    assert looked_up == [1]
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
    live = {"name": "Weapon identity", "directProjectileRaw": {"type": 42, "damage": 11},
            "ammoRaw": {**item["ammoRaw"], "ammoItemRaw": {"type": 97, "damage": 5},
                        "projectileRaw": {"type": 42, "damage": 11},
                        "weaponShootFieldProjectileRaw": {"type": 42, "damage": 11}}}
    live["effectiveProjectileRaw"] = {"type": 43, "damage": 19, "source": "literal native observation"}
    before = copy.deepcopy(live)
    assert parents.compact_ammo_profile(live) == {
        "mode": "weapon_uses_ammo", "ammoId": 97, "ammoItemRaw": {"type": 97, "damage": 5},
        "projectileRaw": {"type": 42}, "weaponShootFieldProjectileRaw": {"type": 42},
        **{key: compact[key] for key in ("playerInventoryAmmoRaw", "playerInventoryProjectileRaw",
                                       "fallbackAmmoRaw", "fallbackProjectileRaw")},
    }
    assert parents.effective_projectile_profile_of(live) == live["effectiveProjectileRaw"]
    raw = raw_parent_card_for_llm(live)["raw"]
    assert raw["effectiveProjectile"] == {"type": 43, "source": "literal native observation"}
    assert raw["directProjectile"]["type"] == 42
    assert raw["ammo"]["ammoItemRaw"]["type"] == 97
    for key in ("playerInventoryAmmoRaw", "playerInventoryProjectileRaw", "fallbackAmmoRaw", "fallbackProjectileRaw"):
        assert raw["ammo"][key] == compact[key]
    assert "exampleAmmo" not in raw["ammo"] and "exampleProjectile" not in raw["ammo"]
    assert live == before


def test_equipment_environment_conditions_survive_every_serialized_stage(offline_packets):
    captured, _ = offline_packets
    equipment = {"source": "certified", "equipmentSourceCertificate": "exact:module",
                 "equippedContributions": {"branches": [{"effects": [{"value": 5, "units": "percentage_points"}]}]},
                 "conditionalArmorSets": [{"condition": {"functionalEquipSlots": {"head": [5, 74], "body": [5, 48], "legs": [5, 44]},
                                                                      "allSlotsRequired": True, "vanitySatisfies": False}, "effects": []}]}
    environment = {"source": "certified", "bannerRegistry": {"enabled": False, "normalDamageDealtMultiplier": 0,
                                                              "nativeBannerIdentities": [87], "condition": "matching active opponent banner"},
                   "unsupported": [], "scope": "not active-world observation"}
    parent = {"name": "source conditions", "nativeEquipmentReference": equipment, "nativeEnvironmentReference": environment}
    before = copy.deepcopy(parent)
    for raw in _source_packets(parent, captured):
        assert raw["item"]["nativeEquipmentReference"] == equipment
        assert raw["item"]["nativeEnvironmentReference"] == environment
    assert parent == before
