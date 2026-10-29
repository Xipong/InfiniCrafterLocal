"""Actual authored jump grants expose presentation without inventing gameplay events."""
from copy import deepcopy

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, EVENT_KIND_REGISTRY, EVENT_KINDS
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_views import runtime_event_inventory
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.schema_validation import strict_schema_errors
from tests.vfx_material_fixtures import _legacy, _sent


def _wire(fn: str) -> dict:
    document = build_capability_witness(fn)
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == fn)
    if fn == "configure_accessory":
        call["params"] = {}
    elif fn == "apply_generated_buff_on_use":
        call["params"] = {"durationSeconds": 10, "lightStrength": 0, "lightColor": "white"}
    call["params"]["playerEffect"] = {"airJump": {
        "count": 2, "launchSpeedBlocksPerSecond": 30, "holdDurationSeconds": .2,
    }}
    report = validate_runtime_program(document)
    assert report["ok"], report
    return compile_runtime_program(document)


def _jump_pairs(wire: dict) -> list[dict]:
    return [row for row in runtime_event_inventory(wire) if row["event"] == "on_jump"]


@pytest.mark.parametrize("fn", ["configure_accessory", "configure_armor", "apply_generated_buff_on_use"])
def test_actual_equipment_and_timed_buff_grants_expose_exact_jump_presentation(fn):
    wire = _wire(fn)
    assert _jump_pairs(wire) == [{"entityId": wire["runtimeProgram"]["itemEntityId"], "event": "on_jump"}]
    before = deepcopy(wire)
    raw = _legacy(wire)
    raw["slots"][0]["event"] = "on_jump"
    assert vfx.validate_vfx_director_output(raw, wire)["ok"]
    packet = _sent(wire, False)
    assert not strict_schema_errors(raw, packet["outputSchema"])
    assert {"entityId": wire["runtimeProgram"]["itemEntityId"], "event": "on_jump"} in packet["runtimeSurface"]["runtimePairs"]
    if fn == "apply_generated_buff_on_use":
        received = packet["acceptedGameplayReadOnly"]["generatedBuff"]["playerEffect"]["airJump"]
    else:
        received = packet["acceptedPlayerEffectsReadOnly"]["armor" if fn == "configure_armor" else "accessory"]["airJump"]
    assert received["count"] == 2 and received["launchSpeedPxPerTick"] == 8
    repair = _sent(wire, True)
    assert repair["acceptedRuntimeProgramReadOnly"] == packet["acceptedRuntimeProgramReadOnly"]
    if fn != "apply_generated_buff_on_use":
        assert repair["acceptedPlayerEffectsReadOnly"] == packet["acceptedPlayerEffectsReadOnly"]
    assert wire == before


def test_jump_presentation_requires_a_reachable_mechanical_grant():
    wire = _wire("configure_accessory")
    raw = _legacy(wire)
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
        assert not vfx.validate_vfx_director_output(raw, unavailable)["ok"]


@pytest.mark.parametrize("anchor", ["tip", "tipHistory"])
def test_jump_vfx_cannot_borrow_unrelated_held_item_geometry(anchor):
    wire = _wire("configure_accessory")
    raw = _legacy(wire)
    raw["slots"][0].update(event="on_jump", anchor=anchor)
    assert strict_schema_errors(raw, _sent(wire, False)["outputSchema"])
    assert not vfx.validate_vfx_director_output(raw, wire)["ok"]
    wire["vfxManifest"] = vfx._compile_manifest(wire, raw, "bad-jump-anchor")
    assert not vfx.validate_vfx_manifest_wire(wire)["ok"]


@pytest.mark.parametrize("consumer", ["binding", "held", "reaction"])
def test_named_buff_jump_presentation_follows_its_exact_group_consumer(consumer):
    wire = _wire("apply_generated_buff_on_use")
    buff = wire["gameplay"].pop("generatedBuff")
    wire["runtimeProgram"]["effectGroups"] = [{"id": "jump_group", "generatedBuff": buff}]
    policy = wire["runtimeProgram"]["bindings"][0]["usePolicy"]
    if consumer == "binding":
        policy["action"]["effectGroupId"] = "jump_group"
    else:
        wire["runtimeProgram"]["bindings"] = []
        if consumer == "held":
            wire["runtimeProgram"]["heldEffectGroupId"] = "jump_group"
        else:
            body = next(row for row in wire["runtimeProgram"]["entities"] if row["kind"] == "item_body")
            body["events"] = [{"action": "apply_generated_buff_on_event", "effectGroupId": "jump_group"}]
    assert _jump_pairs(wire)
    if consumer == "binding":
        policy["action"]["effectGroupId"] = "other_group"
    elif consumer == "held":
        wire["runtimeProgram"]["heldEffectGroupId"] = "other_group"
    else:
        body["events"][0]["effectGroupId"] = "other_group"
    assert not _jump_pairs(wire)


def test_jump_is_canonical_presentation_without_unimplemented_gameplay_dispatch():
    event = EVENT_KIND_REGISTRY["on_jump"]
    assert event.presentation_only and event.producer_player_effect_member == "airJump"
    assert EVENT_KINDS == tuple(name for name, spec in EVENT_KIND_REGISTRY.items() if not spec.presentation_only)
    assert "on_jump" not in CAPABILITY_REGISTRY["spawn_entity_on_event"].allowed_events
    document = build_capability_witness("spawn_entity_on_event")
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn_entity_on_event")
    call["params"]["when"] = "on_jump"
    assert not validate_runtime_program(document)["ok"]
