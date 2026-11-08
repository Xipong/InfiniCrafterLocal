"""Source-defined JSON fixtures, not proof of native capture or executed attacks.

These offline tests certify only the read-only Python handoff. The native writer
owns admission, identity, provenance, coverage and the observation's JSON shape.
"""
from __future__ import annotations

from infini_local.pipelines.visual import request as visual_request


import copy
import json
import socket

import pytest

from infini_local.pipelines.author import request as author
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
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
    from infini_local.pipelines.context.parents import compact_projectile_profile

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


def test_card_selects_current_fields_without_recursive_legacy_hint_scrubbing():
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm

    literal = {"class": "native source member", "tags": [], "semantics": None,
               "nested": [{"canonical": False, "mechanicalHint": "", "behaviorDigest": 0}]}
    parent = {"name": "arbitrary", "nativeEquipmentReference": literal,
              "nativeItemDispatchReference": {"records": [literal, literal]},
              "behaviorDigest": "retired outer metadata", "tags": ["not a mechanic"]}
    before = copy.deepcopy(parent)
    request, _, _ = author.build_initial_author_request(parent, {}, "literal-current-source", model_name="offline")
    raw = expand_native_source_references(request_dossier(request))["parents"]["A"]["packet"]["raw"]
    assert_exact_json(raw["item"]["nativeEquipmentReference"], literal)
    assert_exact_json(raw["item"]["nativeItemDispatchReference"], parent["nativeItemDispatchReference"])
    card = raw_parent_card_for_llm(parent)
    assert "behaviorDigest" not in card and "tags" not in card["raw"]["item"]
    assert_exact_json(parent, before)


def test_retired_parent_profile_probe_and_item_sets_shapes_are_not_admitted(monkeypatch):
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
    from infini_local.services import runtime_dump_service as dumps

    monkeypatch.setattr(dumps, "RUNTIME_DUMP_SNAPSHOT", dumps.RuntimeDumpSnapshot({}, {}, {"status": "absent"}, {}))
    profile = {"type": 42, "timeLeft": 90}
    retired = {"projectileProfile": profile, "runtimeProbeRaw": {"observedHits": 2},
               "itemSetsRaw": {"staff": True}, "setsRaw": {"sword": True},
               "fingerprint": {"projectileProfile": profile}}
    card = raw_parent_card_for_llm(retired)
    assert "directProjectile" not in card["raw"] and "effectiveProjectile" not in card["raw"]
    assert "runtimeProbe" not in card["raw"] and "vanillaFlags" not in card["raw"]
    # Actual current projectile sets remain supported, unlike retired item aliases.
    current = raw_parent_card_for_llm({"directProjectileRaw": {**profile, "setsRaw": {"TrailCacheLength": 7}}})
    assert current["raw"]["directProjectile"]["setsRaw"] == {"TrailCacheLength": 7}


@pytest.mark.parametrize("origin", ["live", "fingerprint", "runtime_dump"])
def test_serialized_author_all_projectile_surfaces_keep_exact_observations(monkeypatch, packet_mode, origin):
    from infini_local.pipelines.context import parents as context
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
        monkeypatch.setattr(context.runtime_dump_service.RuntimeDumpSnapshot, "lookup",
                            lambda self, kind, identity, **kwargs: copy.deepcopy(direct) if kind == "projectile" else {})
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
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
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
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
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
    from tests.generator.authoring.test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit
    observation = source_defined_attack_fixture()
    observation["visual"]["sourceMembers"] = {"class": "native member", "tags": [], "semantics": None}
    parent = {"directProjectileRaw": {"type": 42, "attackReference": observation}}
    child = _accepted_visual_data("workbench_blade")
    before = copy.deepcopy((parent, child))
    captured = []
    _capture_stage(monkeypatch, visual_request, captured)
    scope = {"fieldPermissions": {"itemPaths": ["prompt"], "entities": [], "equipOverlayPaths": []}}
    for repair in (False, True):
        with pytest.raises(_CapturedRequest):
            visual_request._request_visual_kit(child, parent, parent, **({"repair_errors": [
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
    lifetime = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "projectile_lifetime")
    lifetime["params"]["lifetimeSeconds"] = 0
    report = validate_runtime_program(source)
    assert not report["ok"]
    baseline = author.build_gameplay_repair_dossier(source, {}, {}, failure_report=report)
    expected = next(row for row in valid["runtimeProgram"]["calls"] if row["id"] == lifetime["id"])
    candidate = copy.deepcopy(expected)
    # A completely independent valid call must stay frozen.
    independent = copy.deepcopy(next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "item_stats"))
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


def test_attack_packet_size_is_measured_without_runtime_rejection_or_clipping(packet_mode):
    from infini_local.pipelines.author.prompt import (
        PLANNER_PROMPT_LIMIT_CHARS, planner_prompt_usability_report)
    observation = source_defined_attack_fixture()
    parent = {"directProjectileRaw": {"type": 42, "attackReference": observation}}
    report = planner_prompt_usability_report(parent, parent, "source-defined-size")
    request, user, _ = author.build_initial_author_request(parent, parent, "source-defined-size", model_name="offline")
    assert report["ok"] and report["chars"] == len(user) <= PLANNER_PROMPT_LIMIT_CHARS
    print(json.dumps({"scope": "source-defined fixture, not real native capture", "mode": packet_mode,
        "authorPayloadChars": len(user), "developmentTargetChars": PLANNER_PROMPT_LIMIT_CHARS,
        "serializedRequestUtf8Bytes": len(json.dumps(request, ensure_ascii=False).encode("utf-8"))}))
    observation["sourceText"] = "large source-defined unique observation " + "x" * PLANNER_PROMPT_LIMIT_CHARS
    before = copy.deepcopy(parent)
    request, user, _ = author.build_initial_author_request(parent, parent, "source-defined-overflow", model_name="offline")
    assert len(user) > PLANNER_PROMPT_LIMIT_CHARS
    report = planner_prompt_usability_report(parent, parent, "source-defined-overflow")
    assert not report["ok"] and report["headroom"] < 0
    dossier = expand_native_source_references(request_dossier(request))
    for side in ("A", "B"):
        assert_exact_json(dossier["parents"][side]["packet"]["raw"]["directProjectile"]["attackReference"], observation)
    assert_exact_json(parent, before)


# Consumer-specific repair context follows the editable leaf, not ancestry.
@pytest.mark.parametrize("leaf", ["inventoryScale", "scale", "grip.normalizedX"])
def test_sizing_only_visual_repair_excludes_native_attack_but_keeps_size_reference(monkeypatch, packet_mode, leaf):
    import infini_local.pipelines.visual.request as visual_request
    from tests.generator.authoring.test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit
    parent = {"directProjectileRaw": {"type": 42, "attackReference": source_defined_attack_fixture()}}
    parent["spriteReferenceRaw"] = {
        "source": "TextureAssets.Item", "textureWidthPx": 40, "textureHeightPx": 68,
        "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 34, "widthPx": 40, "heightPx": 32}}
    before = copy.deepcopy(parent)
    child = _accepted_visual_data("workbench_blade")
    captured = []
    _capture_stage(monkeypatch, visual_request, captured)
    scope = {"fieldPermissions": {"itemPaths": [leaf] if leaf != "scale" else [],
        "entities": [] if leaf != "scale" else [{"entityId": child["runtimeProgram"]["itemEntityId"], "paths": [leaf]}],
        "equipOverlayPaths": []}}
    with pytest.raises(_CapturedRequest):
        visual_request._request_visual_kit(child, parent, {}, repair_errors=[{"path": "$.item." + leaf}],
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
    import infini_local.pipelines.vfx.prompt as vfx_prompt
    import infini_local.pipelines.vfx.stage as vfx_stage
    from infini_local.pipelines.vfx import request as vfx_transport
    from tests.generator.authoring.test_low_level_three_stage_pipeline import _accepted_visual_data
    child = _accepted_visual_data("workbench_blade")
    parent = {"directProjectileRaw": {"type": 42, "attackReference": source_defined_attack_fixture()}}
    before = copy.deepcopy((child, parent))
    captured = []
    _capture_stage(monkeypatch, vfx_transport, captured)
    monkeypatch.setattr(vfx_transport, "USE_LLM", True)
    packet = vfx_prompt._prompt_packet(child, parent, parent)
    scope = {"allowCreateSlots": True, "fieldPermissions": {"globals": {}, "slots": [], "assets": []}}
    with pytest.raises(_CapturedRequest):
        vfx_stage._request(vfx_transport.call_llm_vfx_director, packet,
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

@pytest.mark.parametrize('dimensions', [(14, 32), (137, 553), (1, 1)])
def test_projectile_loaded_atlas_visual_card_preserves_unknown_layout(dimensions):
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
    reference = {'source': 'TextureAssets.Projectile', 'textureWidthPx': dimensions[0],
                 'textureHeightPx': dimensions[1], 'frameLayout': 'unknown_custom_draw_possible'}
    projectile = {'type': 1, 'width': 7, 'height': 9, 'framesRaw': 1, 'spriteReferenceRaw': reference}
    item = {'type': 40, 'shoot': 1, 'directProjectileRaw': projectile}
    original = copy.deepcopy(item)
    plain = raw_parent_card_for_llm(item)
    visual = raw_parent_card_for_llm(item, include_visual_reference=True)
    assert 'spriteReference' not in plain['raw']['directProjectile']
    observed = visual['raw']['directProjectile'].pop('spriteReference')
    assert observed == reference
    assert 'currentFrame' not in observed
    assert visual == plain
    assert item == original


@pytest.mark.parametrize('reference', [None, {}, {'source': 'TextureAssets.Projectile',
    'textureWidthPx': 12, 'textureHeightPx': 40, 'frameLayout': 'inferred_vertical_strip'},
    {'source': 'TextureAssets.Projectile', 'textureWidthPx': False, 'textureHeightPx': 40,
     'frameLayout': 'unknown_custom_draw_possible'}])
def test_projectile_absent_or_unobserved_atlas_does_not_gain_visual_extent(reference):
    from infini_local.pipelines.context.cards import raw_parent_card_for_llm
    item = {'type': 40, 'shoot': 1, 'directProjectileRaw': {'type': 1, 'width': 999,
            'height': 888, 'framesRaw': 1, 'spriteReferenceRaw': reference}}
    card = raw_parent_card_for_llm(item, include_visual_reference=True)
    assert 'spriteReference' not in card['raw']['directProjectile']


@pytest.mark.parametrize("value", [0, False, 0.0, None, "missing"])
def test_request_source_memo_keeps_literal_types_and_independent_deliveries(value):
    from infini_local.pipelines.context.parents import compact_projectile_profile

    source = source_defined_attack_fixture()
    source["literal"] = 0
    memo = {}
    original = {"type": 42, "source": "direct", "attackReference": source}
    first = compact_projectile_profile(original, attack_source_memo=memo)
    # An envelope's provenance never belongs to the shared transformation.
    other = copy.deepcopy(original)
    other["source"] = "effective"
    expected = compact_projectile_profile(other)
    first["attackReference"]["motion"]["samples"].append("consumer edit")
    second = compact_projectile_profile(other, attack_source_memo=memo)
    assert_exact_json(second, expected)
    assert source["motion"]["samples"] == []
    changed = copy.deepcopy(other)
    if value != "missing":
        changed["attackReference"]["literal"] = value
    else:
        changed["attackReference"].pop("literal")
    third = compact_projectile_profile(changed, attack_source_memo=memo)
    assert_exact_json(third, compact_projectile_profile(changed))
    second["attackReference"]["motion"]["samples"].append("another consumer")
    assert third["attackReference"]["motion"]["samples"] == []


def test_request_source_memo_keeps_member_order_and_unknown_non_json_values():
    from infini_local.pipelines.context.parents import compact_projectile_profile

    memo = {}
    for literal in ({"one": 1, "two": 2}, {"two": 2, "one": 1}, {1: "numeric"}, {"1": "string"}):
        profile = {"type": 42, "attackReference": {"source": "unknown", "literal": literal}}
        assert json.dumps(compact_projectile_profile(profile, attack_source_memo=memo)) == json.dumps(
            compact_projectile_profile(profile))


def test_request_source_memo_keeps_cyclic_unknown_passthrough_detached():
    from infini_local.pipelines.context.parents import compact_projectile_profile

    reference = {"source": "unknown", "literal": []}
    reference["self"] = reference
    profile = {"type": 42, "attackReference": reference}
    expected = compact_projectile_profile(profile)["attackReference"]
    memo = {}
    actual = compact_projectile_profile(profile, attack_source_memo=memo)["attackReference"]
    assert expected["self"] is expected and actual["self"] is actual
    assert actual is not reference
    actual["literal"].append("consumer edit")
    assert reference["literal"] == expected["literal"] == []
    again = compact_projectile_profile(profile, attack_source_memo=memo)["attackReference"]
    assert again["self"] is again and again["literal"] == []


@pytest.mark.parametrize("kind", ["dict", "list"])
def test_request_source_memo_adds_no_recursion_bound_to_unknown_passthrough(kind):
    import subprocess
    import sys
    import textwrap

    # A fresh interpreter avoids pytest/plugin stack depth. Compare the owner's
    # accepted depths instead of prescribing an interpreter-specific cutoff.
    script = textwrap.dedent('''
        import json
        import sys
        from infini_local.pipelines.context.parents import compact_projectile_profile
        sys.setrecursionlimit(1000)
        kind = KIND
        accepted = 0
        for depth in (64, 450, *range(480, 501)):
            value = 0
            for _ in range(depth):
                value = {"child": value} if kind == "dict" else [value]
            profile = {"type": 42, "attackReference": {"source": "unknown", "value": value}}
            before = json.dumps(profile)
            try:
                expected = compact_projectile_profile(profile)
            except RecursionError:
                try:
                    compact_projectile_profile(profile, attack_source_memo={})
                except RecursionError:
                    continue
                raise AssertionError("memo changed the owner's refusal")
            accepted += 1
            actual = compact_projectile_profile(profile, attack_source_memo={})
            assert json.dumps(actual) == json.dumps(expected)
            leaf = actual["attackReference"]["value"]
            for _ in range(depth - 1):
                leaf = leaf["child"] if kind == "dict" else leaf[0]
            if kind == "dict":
                leaf["child"] = "consumer edit"
            else:
                leaf[0] = "consumer edit"
            assert json.dumps(profile) == before
        assert accepted >= 2
    ''').replace("KIND", repr(kind))
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_request_source_memo_copy_failure_recomputes_detached_owner_output(monkeypatch):
    from infini_local.pipelines.context import parents

    profile = {"type": 42, "attackReference": {"source": "unknown", "literal": []}}
    memo = {}
    expected = parents.compact_projectile_profile(profile)
    first = parents.compact_projectile_profile(profile, attack_source_memo=memo)
    cached_tuple = next(iter(memo.values()))
    original_copy = copy.deepcopy

    def copy_with_unavailable_cache(value, *args, **kwargs):
        if value is cached_tuple:
            raise RecursionError("cache tuple cannot be copied in this call stack")
        return original_copy(value, *args, **kwargs)

    monkeypatch.setattr(parents.copy, "deepcopy", copy_with_unavailable_cache)
    actual = parents.compact_projectile_profile(profile, attack_source_memo=memo)
    assert actual == expected
    actual["attackReference"]["literal"].append("consumer edit")
    assert first == expected
    assert profile["attackReference"]["literal"] == []
