"""Source-defined JSON fixtures, not proof of native capture or executed attacks.

These offline tests certify only the read-only Python handoff. The native writer
owns admission, identity, provenance, coverage and the observation's JSON shape.
"""
from __future__ import annotations

import copy
import json
import socket

import pytest

from infini_local.pipelines import llm_authoring_pipeline as author
from prompt_packet_helpers import expand_native_source_references, request_dossier


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("source-defined packet tests forbid network")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture(params=["json_object", "json_schema"])
def packet_mode(monkeypatch, request):
    from infini_local.core import llm_config
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", request.param)
    return request.param


def source_defined_attack_fixture():
    return {
        "source": "source-defined fixture; not native execution evidence",
        "identity": {"fullName": "Fixture/Attack", "projectileType": 42},
        "provenance": {"moduleVersionId": "fixture-module", "methodSha256": "fixture-method"},
        "coverage": [{"method": "AI", "status": "source_observed"},
                     {"method": "PreDraw", "status": "unsupported", "reason": "opaque hook"},
                     {"method": "CanDamage", "status": "unknown", "observations": []}],
        "motion": {"samples": [], "initialSpeed": 0, "accelerates": False},
        "damageCollision": {"multiplier": 0.0, "contact": False, "conditions": [], "optional": None},
        "visual": {"frames": [], "offset": {"x": 0, "y": 0}, "drawDefault": False},
        "scope": "Source observations only; unknown coverage does not mean no effect.",
    }


def assert_exact_json(actual, expected):
    # Python equality aliases False, 0 and 0.0; wire scalar kinds are facts too.
    assert json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_attack_observation_reaches_serialized_author_without_loss_or_parent_mutation():
    observation = source_defined_attack_fixture()
    parent = {"name": "source-defined fixture", "directProjectileRaw": {
        "type": 42, "attackReference": observation}}
    before = copy.deepcopy(parent)
    request, _, _ = author.build_initial_author_request(
        parent, {}, "source-defined-attack", model_name="offline-test-model")
    packet = expand_native_source_references(request_dossier(request))
    sent = packet["parents"]["A"]["packet"]["raw"]["directProjectile"]["attackReference"]
    assert_exact_json(sent, observation)
    sent["motion"]["samples"].append("detached consumer edit")
    assert_exact_json(parent, before)


def test_producer_owned_nested_keys_are_not_stripped_as_derived_parent_hints():
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
    from infini_local.pipelines.parent_context_pipeline import compact_projectile_profile

    observation = source_defined_attack_fixture()
    observation["visual"]["frames"] = [{"class": "Fixture.NativeDraw", "tags": [],
        "semantics": {"source": "literal producer member", "canonical": False},
        "nested": [{"behaviorDigest": "literal member", "mechanicalHint": "", "tags": None}]}]
    parent = {"directProjectileRaw": {"type": 42, "attackReference": observation},
              "behaviorDigest": "untrusted outer hint"}
    before = copy.deepcopy(parent)
    compact = compact_projectile_profile(parent["directProjectileRaw"])
    assert_exact_json(compact["attackReference"], observation)
    for include_visual in (False, True):
        card = raw_parent_card_for_llm(parent, include_visual_reference=include_visual)
        assert_exact_json(card["raw"]["directProjectile"]["attackReference"], observation)
        assert "behaviorDigest" not in card
    compact["attackReference"]["visual"]["frames"].clear()
    assert_exact_json(parent, before)


@pytest.mark.parametrize("origin", ["live", "fingerprint", "runtime_dump"])
def test_serialized_author_all_projectile_surfaces_keep_exact_observations(monkeypatch, packet_mode, origin):
    from infini_local.pipelines import parent_context_pipeline as context
    observation = source_defined_attack_fixture()
    observation["visual"]["frames"] = [{"class": "source literal", "tags": [], "semantics": None}]
    # More than the ordinary compact list/depth boundaries, preserving order and
    # duplicate source statements. No packet test claims these are native facts.
    observation["motion"]["samples"] = [{"index": n, "values": [0, False, 0.0, None, [], {}, ""]}
                                          for n in range(40)]
    direct = {"type": 42, "source": "direct fixture", "attackReference": observation}
    effective = copy.deepcopy(direct)
    effective["attackReference"]["coverage"].append({"status": "unknown", "reason": "effective fixture"})
    ammo = {"mode": "weapon_uses_ammo", "projectileRaw": copy.deepcopy(effective),
            "weaponShootFieldProjectileRaw": copy.deepcopy(effective),
            "playerInventoryProjectileRaw": [direct, direct, effective],
            "fallbackProjectileRaw": [effective, direct],
            "nativeReplacementProjectileRaw": [effective, effective],
            "playerInventoryAmmoRaw": [], "fallbackAmmoRaw": []}
    source = {"directProjectileRaw": direct, "effectiveProjectileRaw": effective, "ammoRaw": ammo}
    if origin == "fingerprint":
        parent = {"name": "fixture", "fingerprint": source}
    elif origin == "runtime_dump":
        parent = {"name": "fixture", "shoot": 42, "ammoRaw": ammo, "effectiveProjectileRaw": effective}
        monkeypatch.setattr(context, "runtime_projectile_lookup", lambda projectile_id: copy.deepcopy(direct))
    else:
        parent = {"name": "fixture", **source}
    before = copy.deepcopy(parent)
    request, user, _ = author.build_initial_author_request(parent, parent, "attack-roster", model_name="offline")
    assert request["response_format"]["type"] == packet_mode
    serialized = json.loads(json.dumps(request, ensure_ascii=False))
    dossier = expand_native_source_references(request_dossier(serialized))
    assert "sourceSameAs" in user, "exercise exact native fact sharing as well as inline packets"
    for side in ("A", "B"):
        raw = dossier["parents"][side]["packet"]["raw"]
        assert_exact_json(raw["directProjectile"], direct)
        assert_exact_json(raw["effectiveProjectile"], effective)
        assert_exact_json(raw["ammo"], ammo)
    assert not any("attackReference" in row["source"] for row in dossier["sourceWireUnits"]["scopes"])
    assert_exact_json(parent, before)


@pytest.mark.parametrize("left,right", [
    ({}, {"coverage": []}),
    ({"coverage": None}, {}),
    ({"value": 0}, {"value": False}),
    ({"value": 0}, {"value": 0.0}),
    ({"coverage": [{"status": "unknown"}]}, {"coverage": [{"status": "unsupported"}]}),
    ({"provenance": {"source": "left"}}, {"provenance": {"source": "right"}}),
    ({"observations": [0, False]}, {"observations": [False, 0]}),
])
def test_distinct_attack_references_never_alias_effective_or_ammo_profiles(packet_mode, left, right):
    direct = {"type": 42, "attackReference": left}
    distinct = {"type": 42, "attackReference": right}
    parent = {"directProjectileRaw": direct, "effectiveProjectileRaw": distinct,
              "ammoRaw": {"projectileRaw": distinct, "weaponShootFieldProjectileRaw": distinct}}
    request, _, _ = author.build_initial_author_request(parent, {}, "distinct-attack", model_name="offline")
    raw = expand_native_source_references(request_dossier(request))["parents"]["A"]["packet"]["raw"]
    assert_exact_json(raw["directProjectile"], direct)
    assert_exact_json(raw["effectiveProjectile"], distinct)
    assert_exact_json(raw["ammo"]["projectileRaw"], distinct)
    assert_exact_json(raw["ammo"]["weaponShootFieldProjectileRaw"], distinct)


def test_identical_attack_profile_alias_retains_only_top_level_source_difference():
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
    observation = source_defined_attack_fixture()
    direct = {"type": 42, "source": "direct fixture", "attackReference": observation}
    same = {**copy.deepcopy(direct), "source": "effective fixture"}
    raw = raw_parent_card_for_llm({"directProjectileRaw": direct, "effectiveProjectileRaw": same,
        "ammoRaw": {"projectileRaw": same, "weaponShootFieldProjectileRaw": same}})["raw"]
    assert_exact_json(raw["directProjectile"], direct)
    expected_alias = {"sameAs": "raw.directProjectile", "source": "effective fixture"}
    assert raw["effectiveProjectile"] == expected_alias
    assert raw["ammo"]["projectileRaw"] == raw["ammo"]["weaponShootFieldProjectileRaw"] == expected_alias


@pytest.mark.parametrize("extra", [{}, {"attackReference": None}, {"attackReference": []}])
def test_missing_attack_observation_is_not_inferred_from_names_ai_or_other_references(extra):
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
    projectile = {"type": 42, "fullName": "Fixture/Attack", "aiStyle": 1,
        "motionReference": {"firstGravityUpdate": 0}, "collisionReference": {"radius": 5}, **extra}
    card = raw_parent_card_for_llm({"directProjectileRaw": projectile})
    assert "attackReference" not in card["raw"]["directProjectile"]
    generated = {"generatedData": {"runtimeProgram": {"entities": [], "bindings": [], "calls": []}},
                 "directProjectileRaw": {"type": 42, "attackReference": source_defined_attack_fixture()}}
    assert "directProjectile" not in raw_parent_card_for_llm(generated)["raw"]


class _CapturedRequest(BaseException):
    """Stop at provider I/O after the real stage serializes its request."""


def _capture_stage(monkeypatch, module, captured):
    def stop(request, **kwargs):
        captured.append(json.loads(json.dumps(request, ensure_ascii=False)))
        raise _CapturedRequest()
    monkeypatch.setattr(module, "resolve_llm_model", lambda: "offline-test-model")
    monkeypatch.setattr(module, "trace_stage_request", lambda *a, **k: None)
    monkeypatch.setattr(module, "llm_chat_json", stop)


def test_attack_reference_survives_actual_visual_director_and_design_repair_requests(monkeypatch, packet_mode):
    from infini_local.pipelines import visual_generation_pipeline as visual
    from test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit
    observation = source_defined_attack_fixture()
    observation["visual"]["sourceMembers"] = {"class": "native member", "tags": [], "semantics": None}
    parent = {"directProjectileRaw": {"type": 42, "attackReference": observation}}
    child = _accepted_visual_data("workbench_blade")
    before = copy.deepcopy((parent, child))
    captured = []
    _capture_stage(monkeypatch, visual, captured)
    scope = {"fieldPermissions": {"itemPaths": ["prompt"], "entities": [], "equipOverlayPaths": []}}
    for repair in (False, True):
        with pytest.raises(_CapturedRequest):
            visual._request_visual_kit(child, parent, parent, **({"repair_errors": [
                {"path": "$.item.prompt", "message": "source-defined invalid prompt"}],
                "previous": _visual_kit(child), "repair_scope": scope} if repair else {}))
    assert len(captured) == 2
    for index, request in enumerate(captured):
        assert request["response_format"]["type"] == packet_mode
        dossier = request_dossier(request)
        parents = dossier["parentFactsReadOnly" if index else "parents"]
        for side in ("parentA", "parentB"):
            assert_exact_json(parents[side]["packet"]["raw"]["directProjectile"]["attackReference"], observation)
        if not index:
            assert_exact_json(dossier["acceptedPresentationMechanicsReadOnly"]["gameplay"]["itemScale"],
                              child["gameplay"]["itemScale"])
    assert_exact_json(request_dossier(captured[1])["repairScope"], scope)
    assert_exact_json((parent, child), before)


def test_native_attack_context_does_not_widen_actual_frozen_gameplay_repair(monkeypatch, packet_mode):
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from repair_test_helpers import repair_with_response
    observation = source_defined_attack_fixture()
    parent = {"directProjectileRaw": {"type": 42, "attackReference": observation}}
    source = build_runtime_fixture("workbench_blade")
    valid = copy.deepcopy(source)
    lifetime = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "set_projectile_lifetime")
    lifetime["params"]["lifetimeSeconds"] = 0
    report = validate_runtime_program(source)
    assert not report["ok"]
    baseline = author.build_gameplay_repair_dossier(source, {}, {}, failure_report=report)
    expected = next(row for row in valid["runtimeProgram"]["calls"] if row["id"] == lifetime["id"])
    candidate = copy.deepcopy(expected)
    # A completely independent valid call must stay frozen.
    independent = copy.deepcopy(next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats"))
    independent["params"]["damage"] += 11
    before = copy.deepcopy((source, parent))
    repaired, request = repair_with_response(monkeypatch, source,
        {"note": "source-defined fixture response, lifetime only", "callsUpsert": [candidate, independent]},
        packet_mode, out_of_scope_response=True, parents=(parent, parent))
    dossier = expand_native_source_references(request_dossier(request))
    for side in ("a", "b"):
        assert_exact_json(dossier["parents"][side]["packet"]["raw"]["directProjectile"]["attackReference"], observation)
    assert_exact_json(dossier["repairScope"], baseline["repairScope"])
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": lifetime["id"], "paths": ["params.lifetimeSeconds"]}]
    assert_exact_json(dossier["acceptedItemContext"]["runtimeProgram"], source["runtimeProgram"])
    assert_exact_json(repaired["runtimeProgram"], valid["runtimeProgram"])
    assert any(row["reason"] == "independent_valid_node_frozen"
               for row in repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"])
    assert_exact_json((source, parent), before)


def test_attack_packet_size_is_measured_and_existing_guard_refuses_instead_of_clipping(packet_mode):
    from infini_local.pipelines.llm_authoring_prompt import (
        PLANNER_PROMPT_LIMIT_CHARS, planner_prompt_usability_report)
    observation = source_defined_attack_fixture()
    parent = {"directProjectileRaw": {"type": 42, "attackReference": observation}}
    report = planner_prompt_usability_report(parent, parent, "source-defined-size")
    request, user, _ = author.build_initial_author_request(parent, parent, "source-defined-size", model_name="offline")
    assert report["ok"] and report["chars"] == len(user) <= PLANNER_PROMPT_LIMIT_CHARS
    print(json.dumps({"scope": "source-defined fixture, not real native capture", "mode": packet_mode,
        "authorPayloadChars": len(user), "guardChars": PLANNER_PROMPT_LIMIT_CHARS,
        "serializedRequestUtf8Bytes": len(json.dumps(request, ensure_ascii=False).encode("utf-8"))}))
    observation["sourceText"] = "large source-defined unique observation " + "x" * PLANNER_PROMPT_LIMIT_CHARS
    before = copy.deepcopy(parent)
    with pytest.raises(ValueError, match="above configured"):
        author.build_initial_author_request(parent, parent, "source-defined-overflow", model_name="offline")
    assert_exact_json(parent, before)


# Consumer-specific repair context follows the editable leaf, not ancestry.
@pytest.mark.parametrize("leaf", ["inventoryScale", "scale", "grip.normalizedX"])
def test_sizing_only_visual_repair_excludes_native_attack_but_keeps_size_reference(monkeypatch, packet_mode, leaf):
    from infini_local.pipelines import visual_generation_pipeline as visual
    from test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit
    parent = {"directProjectileRaw": {"type": 42, "attackReference": source_defined_attack_fixture()}}
    parent["spriteReferenceRaw"] = {
        "source": "TextureAssets.Item", "textureWidthPx": 40, "textureHeightPx": 68,
        "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 34, "widthPx": 40, "heightPx": 32}}
    before = copy.deepcopy(parent)
    child = _accepted_visual_data("workbench_blade")
    captured = []
    _capture_stage(monkeypatch, visual, captured)
    scope = {"fieldPermissions": {"itemPaths": [leaf] if leaf != "scale" else [],
        "entities": [] if leaf != "scale" else [{"entityId": child["runtimeProgram"]["itemEntityId"], "paths": [leaf]}],
        "equipOverlayPaths": []}}
    with pytest.raises(_CapturedRequest):
        visual._request_visual_kit(child, parent, {}, repair_errors=[{"path": "$.item." + leaf}],
            previous=_visual_kit(child), repair_scope=scope)
    packet = request_dossier(captured[0])
    assert "parentFactsReadOnly" not in packet
    assert "attackReference" not in json.dumps(packet)
    assert_exact_json(packet["parentSizeReferencesReadOnly"]["parentA"]["spriteReference"], parent["spriteReferenceRaw"])
    assert_exact_json(parent, before)
    assert packet["acceptedPresentationMechanicsReadOnly"]
    assert_exact_json(packet["repairScope"], scope)


@pytest.mark.parametrize("repair", [False, True], ids=["director", "repair"])
def test_attack_observation_reaches_actual_vfx_parent_context(monkeypatch, packet_mode, repair):
    from infini_local.core import vfx_manifest as vfx
    from infini_local.pipelines import vfx_generation_pipeline as vfx_transport
    from test_low_level_three_stage_pipeline import _accepted_visual_data
    child = _accepted_visual_data("workbench_blade")
    parent = {"directProjectileRaw": {"type": 42, "attackReference": source_defined_attack_fixture()}}
    before = copy.deepcopy((child, parent))
    captured = []
    _capture_stage(monkeypatch, vfx_transport, captured)
    monkeypatch.setattr(vfx_transport, "USE_LLM", True)
    packet = vfx._prompt_packet(child, parent, parent)
    scope = {"allowCreateSlots": True, "fieldPermissions": {"globals": {}, "slots": [], "assets": []}}
    with pytest.raises(_CapturedRequest):
        vfx._request(vfx_transport.call_llm_vfx_director, packet,
            **({"repair_errors": [], "previous": {}, "repair_scope": scope} if repair else {}))
    dossier = request_dossier(captured[0])
    parents = dossier["parentFactsReadOnly" if repair else "parents"]
    assert len(parents) == 2
    for source in parents:
        assert_exact_json(source["packet"]["raw"]["directProjectile"]["attackReference"],
                          parent["directProjectileRaw"]["attackReference"])
    if repair:
        assert_exact_json(dossier["repairScope"], scope)
    assert_exact_json(dossier["acceptedRuntimeProgramReadOnly"], child["runtimeProgram"] | {
        "entities": [{k: v for k, v in entity.items() if k != "visual"} for entity in child["runtimeProgram"]["entities"]]})
    assert_exact_json((child, parent), before)
