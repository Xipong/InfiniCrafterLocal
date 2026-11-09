"""Actual authored jump grants expose presentation without inventing gameplay events."""
from copy import deepcopy

import pytest

from infini_local.core.vfx.projection import _compile_manifest
from infini_local.core.vfx.validation import validate_vfx_director_output, validate_vfx_manifest_wire
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, EVENT_KIND_REGISTRY, EVENT_KINDS
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_views import runtime_event_inventory
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.schema_validation import strict_schema_errors
from vfx_material_fixtures import _shape, _sent


def _wire(fn: str) -> dict:
    document = build_capability_witness(fn)
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == fn)
    if fn == "accessory":
        call["params"] = {}
    elif fn == "generated_buff_on_use":
        call["params"] = {"duration": 10, "lightStrength": 0, "lightColor": "white"}
    call["params"]["playerEffect"] = {"airJump": {
        "count": 2, "launchSpeedBlocksPerSecond": 30, "holdDurationSeconds": .2,
    }}
    report = validate_runtime_program(document)
    assert report["ok"], report
    return compile_runtime_program(document)


def _jump_pairs(wire: dict) -> list[dict]:
    return [row for row in runtime_event_inventory(wire) if row["event"] == "on_jump"]


@pytest.mark.parametrize("fn", ["accessory", "armor", "generated_buff_on_use"])
def test_actual_equipment_and_timed_buff_grants_expose_exact_jump_presentation(fn):
    wire = _wire(fn)
    assert _jump_pairs(wire) == [{"entityId": wire["runtimeProgram"]["itemEntityId"], "event": "on_jump"}]
    before = deepcopy(wire)
    raw = _shape(wire)
    raw["slots"][0]["event"] = "on_jump"
    assert validate_vfx_director_output(raw, wire)["ok"]
    packet = _sent(wire, False)
    assert not strict_schema_errors(raw, packet["outputSchema"])
    assert {"entityId": wire["runtimeProgram"]["itemEntityId"], "event": "on_jump"} in packet["runtimeSurface"]["runtimePairs"]
    if fn == "generated_buff_on_use":
        received = packet["acceptedGameplayReadOnly"]["generatedBuff"]["playerEffect"]["airJump"]
    else:
        received = packet["acceptedPlayerEffectsReadOnly"]["armor" if fn == "armor" else "accessory"]["airJump"]
    assert received["count"] == 2 and received["launchSpeedPxPerTick"] == 8
    repair = _sent(wire, True)
    assert repair["acceptedRuntimeProgramReadOnly"] == packet["acceptedRuntimeProgramReadOnly"]
    if fn != "generated_buff_on_use":
        assert repair["acceptedPlayerEffectsReadOnly"] == packet["acceptedPlayerEffectsReadOnly"]
    assert wire == before


def test_jump_presentation_requires_a_reachable_mechanical_grant():
    wire = _wire("accessory")
    raw = _shape(wire)
    raw["slots"][0]["event"] = "on_jump"
    for mutation in ("no_binding", "disabled", "no_jump"):
        unavailable = deepcopy(wire)
        if mutation == "no_binding":
            unavailable["runtimeProgram"]["bindings"] = []
        elif mutation == "disabled":
            unavailable["accessory"]["enabled"] = False
        else:
            unavailable["accessory"]["playerEffect"].pop("airJump")
        assert not _jump_pairs(unavailable)
        assert not validate_vfx_director_output(raw, unavailable)["ok"]


@pytest.mark.parametrize("anchor", ["tip", "tipHistory"])
def test_jump_vfx_cannot_borrow_unrelated_held_item_geometry(anchor):
    wire = _wire("accessory")
    raw = _shape(wire)
    raw["slots"][0].update(event="on_jump", anchor=anchor)
    assert strict_schema_errors(raw, _sent(wire, False)["outputSchema"])
    assert not validate_vfx_director_output(raw, wire)["ok"]
    wire["vfxManifest"] = _compile_manifest(wire, raw, "bad-jump-anchor")
    assert not validate_vfx_manifest_wire(wire)["ok"]


@pytest.mark.parametrize("consumer", ["binding", "held", "reaction"])
def test_named_buff_jump_presentation_follows_its_exact_group_consumer(consumer):
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

    document = build_capability_witness({"binding": "generated_buff_on_use", "held": "refresh_held_effect",
                                         "reaction": "generated_buff_on_event"}[consumer])
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "generated_buff_on_use")
    call["params"]["playerEffect"] = {"airJump": {
        "count": 2, "launchSpeedBlocksPerSecond": 30, "holdDurationSeconds": .2,
    }}
    if consumer == "binding":
        call["params"]["effectGroupId"] = "jump_group"
        document["runtimeProgram"]["bindings"][0]["action"]["effectGroupId"] = "jump_group"
    wire = compile_runtime_program(document)
    assert validate_runtime_wire(wire)["ok"]
    assert _jump_pairs(wire) == [{"entityId": wire["runtimeProgram"]["itemEntityId"], "event": "on_jump"}]
    raw = _shape(wire)
    raw["slots"][0]["event"] = "on_jump"
    assert validate_vfx_director_output(raw, wire)["ok"]
    if consumer == "binding":
        wire["runtimeProgram"]["bindings"][0]["usePolicy"]["action"]["effectGroupId"] = "other_group"
    elif consumer == "held":
        wire["runtimeProgram"]["heldEffectGroupId"] = "other_group"
    else:
        body = next(row for row in wire["runtimeProgram"]["entities"] if row["kind"] == "item_body")
        body["events"][0]["effectGroupId"] = "other_group"
    assert not _jump_pairs(wire)
    assert not validate_vfx_director_output(raw, wire)["ok"]


def test_jump_is_canonical_presentation_without_unimplemented_gameplay_dispatch():
    event = EVENT_KIND_REGISTRY["on_jump"]
    assert event.presentation_only and event.producer_player_effect_member == "airJump"
    assert EVENT_KINDS == tuple(name for name, spec in EVENT_KIND_REGISTRY.items() if not spec.presentation_only)
    assert "on_jump" not in CAPABILITY_REGISTRY["spawn_on_event"].allowed_events
    document = build_capability_witness("spawn_on_event")
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn_on_event")
    call["params"]["when"] = "on_jump"
    assert not validate_runtime_program(document)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("correction", ["anchor", "noop"])
def test_jump_anchor_repair_is_serialized_leaf_local_and_preserves_mechanics(monkeypatch, correction, mode):
    from math import pi

    from infini_local.core import llm_config
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines.vfx import prompt, request, stage
    from prompt_packet_helpers import request_dossier
    from tests.generator.vfx.test_repair_vfx_contract import _offline_transport, _patch
    from tests.generator.runtime.test_source_unit_guidance import _serialized_chat_request

    wire = _wire("accessory")
    before = deepcopy(wire)
    raw = _shape(wire)
    raw["slots"][0]["event"] = "on_jump"
    raw["slots"][0]["shape"].update(offsetForwardPx=-18, offsetSidePx=7.5, rotationRadians=pi / 2)
    assert validate_vfx_director_output(raw, wire)["ok"]
    raw["slots"][0]["anchor"] = "tip"
    candidate = deepcopy(raw["slots"][0])
    candidate.update(anchor="hitPoint", duration=1)
    candidate["shape"].update(radiusEndPx=1, offsetForwardPx=0, offsetSidePx=0, rotationRadians=0)
    patch = _patch(slotsUpsert=[candidate]) if correction == "anchor" else _patch()
    requests = _offline_transport(monkeypatch, "air_jump_anchor_" + correction, [raw, patch])
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    if correction == "noop":
        with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
            stage.attach_vfx_manifest(wire, "jump-repair", llm_director=request.call_llm_vfx_director)
        assert "vfxManifest" not in wire
    else:
        result = stage.attach_vfx_manifest(wire, "jump-repair", llm_director=request.call_llm_vfx_director)
        expected = deepcopy(raw)
        expected["slots"][0]["anchor"] = "hitPoint"
        assert result["debug"]["vfxDirectorRaw"] == expected
        assert result["vfxManifest"] == _compile_manifest(before, expected, "jump-repair")
        assert validate_vfx_manifest_wire(result)["ok"]
        assert result["debug"]["vfxRepairFilterAudit"]["ignoredChanges"]
    assert len(requests) == 2
    director, repair = map(request_dossier, requests)
    assert repair["repairScope"]["fieldPermissions"] == {
        "globals": {}, "slots": [{"slotId": raw["slots"][0]["id"], "paths": ["anchor"]}], "assets": [],
    }
    assert repair["acceptedPlayerEffectsReadOnly"] == director["acceptedPlayerEffectsReadOnly"]
    assert repair["acceptedRuntimeProgramReadOnly"] == director["acceptedRuntimeProgramReadOnly"]
    for fragment in (
        "native ExtraJump start", "ground jumps, landings", "origin=player.Center", "not feet",
        "forward=(0,-player.gravDir)", "normal=(-forward.Y,forward.X)",
        "normal gravity +X", "inverted gravity -X", "self/owner/field/hitPoint",
        "facing, itemRotation and itemLocation", "actual captured/live player velocity",
        "normalized", "zero velocity", "world attachment freezes the event-time frame",
        "source attachment follows the exact live grant and current gravity",
        "negative forward offsets point toward the feet", "tip/tipHistory are forbidden",
        "Offsets and rotations remain authored",
    ):
        assert fragment in prompt._AIR_JUMP_RULE
    for built_request, dossier in zip(requests, (director, repair)):
        assert dossier["rules"].count(prompt._AIR_JUMP_RULE) == 1
        serialized = _serialized_chat_request(monkeypatch, built_request)
        assert serialized["response_format"]["type"] == mode
        # Inspect actual HTTP-serialized messages, not stripped provider schema annotations.
        assert sum(prompt._AIR_JUMP_RULE in message["content"] for message in serialized["messages"]) == 1
    assert {key: wire[key] for key in before if key != "debug"} == {key: value for key, value in before.items() if key != "debug"}
