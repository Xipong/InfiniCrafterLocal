"""The JSON actually sent to VFX Director/Repair names units at each authored field."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.core import vfx_manifest as vfx


_GLOBAL_DESCRIPTIONS = {
    "effectMagnitude": ("no renderer consumer", "metadata"),
}
_MOTIF_DESCRIPTIONS = {
    "rhythm": ("no renderer consumer", "metadata"),
    "chaos": ("no renderer consumer", "metadata"),
}
_SLOT_DESCRIPTIONS = {
    "scale": ("renderer", "projectile.scale", "thickness", "light", "dust"),
    "density": ("projectile", "item", "count", "repeatevery"),
    "duration": ("impactSprite", "world ticks", "only"),
    "alpha": ("draw", "sound", "dust", "clamp"),
    "spread": ("speed", "not angle", "projectile", "item"),
    "jitter": ("no renderer consumer",),
    "fadeIn": ("no renderer consumer",),
    "fadeOut": ("no renderer consumer",),
    "budgetWeight": ("no renderer consumer",),
    "signatureWeight": ("no renderer consumer",),
    "visualCost": ("no renderer consumer",),
    "startTick": ("projectile", "periodic", "only", "world tick"),
    "repeatEvery": ("periodic", "0", "automatic", "projectile", "item", "world tick"),
}
_EXPECTED_BOUNDS = {
    "scale": ("number", 0.15, 5.0), "density": ("number", 0.0, 1.0),
    "duration": ("integer", 3, 120), "alpha": ("number", 0.0, 1.0),
    "spread": ("number", 0.0, 2.0), "jitter": ("number", 0.0, 1.5),
    "fadeIn": ("number", 0.0, 0.8), "fadeOut": ("number", 0.0, 0.8),
    "budgetWeight": ("number", 0.1, 4.0), "signatureWeight": ("number", 0.0, 1.0),
    "visualCost": ("number", 0.0, 1.0), "startTick": ("integer", 0, 120),
    "repeatEvery": ("integer", 0, 120),
}


def _decoded_packet(repair: bool) -> dict:
    packet = vfx._prompt_packet({}, None, None)
    if not repair:
        sent = []
        vfx._request(lambda system, user, *args, **kwargs: sent.append(user) or {}, packet)
        return json.loads(json.dumps(sent[0]))
    sent = []
    vfx._request(
        lambda system, user, *args, **kwargs: sent.append(kwargs["messages"][1]["content"]) or {},
        packet, repair_errors=[{"path": "$.slots[0].spread", "message": "invalid"}],
        previous={"slots": []}, repair_scope={"fieldPermissions": {"slots": []}},
    )
    return json.loads(sent[0])


@pytest.mark.parametrize("repair", [False, True])
def test_serialized_vfx_schema_describes_every_authored_numeric_at_its_field(repair: bool) -> None:
    output = _decoded_packet(repair)["outputSchema"]["properties"]
    globals_ = output["effectMagnitude"]["anyOf"][0] if repair else output["effectMagnitude"]
    motif = output["motif"]["anyOf"][0]["properties"] if repair else output["motif"]["properties"]
    slot = output["slotsUpsert"]["items"]["properties"] if repair else output["slots"]["items"]["properties"]
    for field, terms in _GLOBAL_DESCRIPTIONS.items():
        description = globals_["description"].lower()
        assert "engine units" in description
        assert all(term.lower() in description for term in terms), (field, description)
    for field, terms in _MOTIF_DESCRIPTIONS.items():
        description = motif[field]["description"].lower()
        assert "engine units" in description
        assert all(term.lower() in description for term in terms), (field, description)
    assert set(_SLOT_DESCRIPTIONS) == set(_EXPECTED_BOUNDS)
    for field, terms in _SLOT_DESCRIPTIONS.items():
        description = slot[field]["description"].lower()
        if field not in {"duration", "startTick", "repeatEvery"}:
            assert "engine units" in description
        assert all(term.lower() in description for term in terms), (field, description)
        assert {key: slot[field][key] for key in ("type", "minimum", "maximum")} == dict(zip(("type", "minimum", "maximum"), _EXPECTED_BOUNDS[field]))
    assert {key: globals_[key] for key in ("type", "minimum", "maximum")} == {"type": "number", "minimum": 0.0, "maximum": 1.0}
    for field, bounds in {"rhythm": ("number", 0.2, 3.0), "chaos": ("number", 0.0, 1.0)}.items():
        assert {key: motif[field][key] for key in ("type", "minimum", "maximum")} == dict(zip(("type", "minimum", "maximum"), bounds))


def test_numeric_descriptions_leave_keys_bounds_and_decoded_values_unchanged() -> None:
    data = {"runtimeProgram": {"entities": [{
        "id": "item_body", "kind": "item_body", "visualRole": "item",
        "events": [{"event": "periodic"}],
    }]}}
    packet = vfx._prompt_packet(data, None, None)
    normal = packet["outputSchema"]
    repair = vfx._vfx_repair_schema_from_packet(packet)
    standalone_repair = vfx.vfx_repair_schema(data)
    original_slot = normal["properties"]["slots"]["items"]
    repair_slot = repair["properties"]["slotsUpsert"]["items"]
    assert repair_slot == original_slot == standalone_repair["properties"]["slotsUpsert"]["items"]
    assert repair["properties"]["motif"]["anyOf"][0] == normal["properties"]["motif"]
    assert repair["properties"]["effectMagnitude"]["anyOf"][0] == normal["properties"]["effectMagnitude"]
    assert set(original_slot["properties"]) == set(original_slot["required"])
    assert set(normal["properties"]) == set(normal["required"])
    assert packet["runtimeSurface"]["numericRanges"] == {
        "effectMagnitude": [0.0, 1.0], "scale": [0.15, 5.0],
        "density": [0.0, 1.0], "duration": [3, 120], "alpha": [0.0, 1.0],
        "spread": [0.0, 2.0], "jitter": [0.0, 1.5], "fadeIn": [0.0, 0.8],
        "fadeOut": [0.0, 0.8], "budgetWeight": [0.1, 4.0],
        "signatureWeight": [0.0, 1.0], "visualCost": [0.0, 1.0],
        "startTick": [0, 120], "repeatEvery": [0, 120],
    }
    pair = packet["runtimeSurface"]["runtimePairs"][0]
    slot = {key: (schema["enum"][0] if "enum" in schema else "") for key, schema in original_slot["properties"].items()}
    slot.update({
        "id": "numeric_witness", **pair, "rendererKind": "impactRing",
        "scale": 2.75, "density": 0.36, "duration": 41, "alpha": 0.64,
        "spread": 1.25, "jitter": 0.9, "fadeIn": 0.2, "fadeOut": 0.3,
        "budgetWeight": 1.75, "signatureWeight": 0.44, "visualCost": 0.23,
        "startTick": 19, "repeatEvery": 0,
    })
    authored = {"schema": vfx.VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.42,
                "visualBudgetClass": "normal", "motif": {
                    "element": "fire", "shapeLanguage": "ring", "motionLanguage": "outward",
                    "paletteRole": "primary", "rhythm": 1.9, "chaos": 0.73,
                }, "slots": [slot]}
    report = vfx.validate_vfx_director_output(copy.deepcopy(authored), data)
    assert report["ok"], report["errors"]
    assert report["normalized"]["effectMagnitude"] == authored["effectMagnitude"]
    assert report["normalized"]["motif"] == authored["motif"]
    for field in _EXPECTED_BOUNDS:
        assert report["normalized"]["slots"][0][field] == authored["slots"][0][field]
