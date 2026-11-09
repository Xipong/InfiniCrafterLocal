"""Native held-body visibility is one authored flag, not a placement mode."""
from copy import deepcopy
import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def authored():
    document = build_runtime_fixture("umbrella_grenade")
    use = next(c for c in document["runtimeProgram"]["calls"] if c["fn"] == "item_use")
    return document, use["params"]


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("style", ["shoot", "swing", "thrust"])
def test_native_visibility_preserves_style_and_gesture(hidden, style):
    document, params = authored()
    params.update(hideUseGraphic=hidden, useStyle=style)
    frozen = deepcopy(document)
    report = validate_runtime_program(document)
    assert report["ok"], report
    wire = compile_runtime_program(document)
    assert document == frozen
    use = wire["runtimeProgram"]["itemUse"]
    assert use["hideUseGraphic"] is hidden
    assert use["useStyle"] == style
    assert use.get("handPose") == params.get("handPose")
    assert "heldAlignment" not in use and "releaseTiming" not in use
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    assert any(r.get("finalPath") == "runtimeProgram.itemUse.hideUseGraphic" and r.get("value") is hidden for r in wire["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("field,value", [("heldAlignment", "grip"), ("heldAlignment", "native_frame"), ("heldAlignment", None), ("customHeldSprite", "visible"), ("customHeldSprite", "hidden"), ("customHeldSprite", "inherit")])
def test_removed_author_choices_reject_without_migration(field, value):
    document, params = authored()
    params[field] = value
    frozen = deepcopy(document)
    assert not validate_runtime_program(document)["ok"]
    assert document == frozen


@pytest.mark.parametrize("field,value", [("heldAlignment", "grip"), ("heldAlignment", "native_frame"), ("releaseTiming", ""), ("releaseTiming", "immediate"), ("releaseTiming", "on_release")])
def test_removed_wire_choices_reject_without_migration(field, value):
    document, _ = authored()
    wire = compile_runtime_program(document)
    wire["runtimeProgram"]["itemUse"][field] = value
    frozen = deepcopy(wire)
    assert not validate_runtime_wire(wire)["ok"]
    assert wire == frozen


@pytest.mark.parametrize("value", [None, "true", 1, {}, []])
def test_native_visibility_requires_boolean(value):
    document, params = authored()
    params["hideUseGraphic"] = value
    assert not validate_runtime_program(document)["ok"]
