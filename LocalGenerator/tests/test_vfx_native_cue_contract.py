from __future__ import annotations

import copy
import math
import pytest

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx.native_cues import (
    NATIVE_DUST_TYPES, native_cue_errors, native_cue_slot_clauses,
    native_dust_schema, native_light_schema,
)


def dust():
    return {"spawn": {"shape": "point"}, "type": "Smoke", "count": 5, "size": .75, "speedMinPxPerTick": 2,
            "speedMaxPxPerTick": 3, "spreadRadians": math.tau, "inheritVelocity": .25,
            "angularDistribution": "random", "directionFrame": "source", "angleOffsetRadians": 0,
            "nativeAlpha": 100, "noGravity": False}


@pytest.mark.parametrize("kind", NATIVE_DUST_TYPES)
def test_explicit_native_types_and_independent_values_preserved(kind):
    payload = dust()
    payload["type"] = kind
    before = copy.deepcopy(payload)
    assert not native_cue_errors({"rendererKind": "nativeDust", "dust": payload})
    assert payload == before


@pytest.mark.parametrize("field", list(dust()))
def test_every_dust_choice_is_required(field):
    payload = dust()
    del payload[field]
    assert native_cue_errors({"rendererKind": "nativeDust", "dust": payload})


@pytest.mark.parametrize("field,value", [
    ("count", True), ("count", 1.5), ("count", 65), ("size", -1), ("size", float("nan")),
    ("speedMinPxPerTick", float("inf")), ("speedMaxPxPerTick", 25),
    ("spreadRadians", -1), ("inheritVelocity", 2), ("nativeAlpha", 256),
    ("nativeAlpha", 0.5), ("noGravity", 1), ("type", "none"), ("density", .5),
])
def test_invalid_choices_rejected_without_normalization(field, value):
    payload = dust()
    payload[field] = value
    assert native_cue_errors({"rendererKind": "nativeDust", "dust": payload})


def test_inverted_speed_is_not_repaired():
    payload = dust()
    payload.update(speedMinPxPerTick=5, speedMaxPxPerTick=2)
    assert native_cue_errors({"rendererKind": "nativeDust", "dust": payload})
    assert payload["speedMinPxPerTick"] == 5


def test_silence_and_boundary_values_are_valid():
    payload = dust()
    payload.update(count=0, size=0, speedMinPxPerTick=0, speedMaxPxPerTick=0,
                   spreadRadians=0, inheritVelocity=0, nativeAlpha=255, noGravity=True)
    assert not native_cue_errors({"rendererKind": "nativeDust", "dust": payload})
    for value in (0, 1.2):
        assert not native_cue_errors({"rendererKind": "nativeLight", "light": {"intensity": value}})
    for payload in ({}, {"intensity": True}, {"intensity": -1}, {"intensity": 1.21}, {"intensity": 1, "scale": 1}):
        assert native_cue_errors({"rendererKind": "nativeLight", "light": payload})


def slot_schema():
    return {"type": "object", "properties": {"dust": native_dust_schema(), "light": native_light_schema()},
            "allOf": native_cue_slot_clauses(["body"], ["nativeDust", "nativeLight", "soundCue"], ["periodic", "on_use"])}


def slot():
    return {"rendererKind": "nativeDust", "dust": dust(), "entityId": "projectile",
            "event": "periodic", "color": {"r": 1, "g": 2, "b": 3}, "startTick": 5, "repeatEvery": 4}


def test_exact_cadence_and_event_delay():
    value = slot()
    assert not strict_schema_errors(value, slot_schema())
    value["repeatEvery"] = 0
    assert strict_schema_errors(value, slot_schema())
    value["event"] = "on_use"
    assert not strict_schema_errors(value, slot_schema())  # Delayed event valid.
    value.update(event="periodic", repeatEvery=1, entityId="body")
    assert strict_schema_errors(value, slot_schema())
    value["startTick"] = 0
    assert not strict_schema_errors(value, slot_schema())


@pytest.mark.parametrize("field", ["scale", "density", "spread", "alpha", "duration", "phaseOffset", "particleSystemId", "blend", "layer", "textureRole"])
def test_legacy_controls_cannot_leak_into_new_cues(field):
    value = slot()
    value[field] = 0
    assert strict_schema_errors(value, slot_schema())


def test_payload_exclusivity():
    value = slot()
    value["light"] = {"intensity": 1}
    assert strict_schema_errors(value, slot_schema())
    value.pop("light")
    value["rendererKind"] = "soundCue"
    assert strict_schema_errors(value, slot_schema())


def test_errors_have_exact_repair_leaf_paths_and_native_bounds():
    import struct
    payload = dust()
    payload.update(speedMinPxPerTick=5, speedMaxPxPerTick=2)
    errors = native_cue_errors({"rendererKind": "nativeDust", "dust": payload}, "$.slots[3]")
    assert errors == [{"path": "$.slots[3].dust.speedMaxPxPerTick", "message": "must be >= speedMinPxPerTick"}]
    payload = dust()
    payload["spreadRadians"] = struct.unpack("<f", struct.pack("<f", math.tau))[0]
    assert native_cue_errors({"rendererKind": "nativeDust", "dust": payload})
    assert not native_cue_errors({"rendererKind": "nativeDust", "dust": payload}, persisted_wire=True)
    payload["count"] = True
    errors = native_cue_errors({"rendererKind": "nativeDust", "dust": payload}, persisted_wire=True)
    assert all(set(error) == {"path", "message"} for error in errors)
    assert errors[0]["path"] == "$.dust.count"


@pytest.mark.parametrize("distribution", ["random", "even"])
@pytest.mark.parametrize("frame", ["world", "source"])
def test_dust_distribution_and_frame_are_explicit_independent_choices(distribution, frame):
    payload = dust()
    payload.update(angularDistribution=distribution, directionFrame=frame, angleOffsetRadians=math.pi)
    before = copy.deepcopy(payload)
    assert not native_cue_errors({"rendererKind": "nativeDust", "dust": payload})
    assert payload == before


def test_saved_native_dust_missing_new_fields_remains_unchanged():
    payload = dust()
    for field in ("angularDistribution", "directionFrame", "angleOffsetRadians"):
        payload.pop(field)
    before = copy.deepcopy(payload)
    slot = {"rendererKind": "nativeDust", "dust": payload}
    assert native_cue_errors(slot)
    assert not native_cue_errors(slot, persisted_wire=True)
    assert payload == before


@pytest.mark.parametrize("field,value", [("angularDistribution", "automatic"), ("directionFrame", "guessed"),
                                         ("angleOffsetRadians", 7), ("angleOffsetRadians", float("nan"))])
def test_invalid_new_dust_choices_never_fall_back_even_in_saved_wire(field, value):
    payload = dust()
    payload[field] = value
    slot = {"rendererKind": "nativeDust", "dust": payload}
    assert native_cue_errors(slot)
    assert native_cue_errors(slot, persisted_wire=True)
