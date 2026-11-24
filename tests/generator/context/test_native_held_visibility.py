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
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    assert any(r.get("finalPath") == "runtimeProgram.itemUse.hideUseGraphic" and r.get("value") is hidden for r in wire["runtimeContract"]["finalWireReceipts"])


def test_item_use_refuses_unknown_author_input_without_discarding_it():
    document, params = authored()
    params["unexpectedField"] = 42
    frozen = deepcopy(document)
    report = validate_runtime_program(document)
    assert not report["ok"]
    assert any(error["code"] == "shape_additional_property"
               and error["path"].endswith(".params.unexpectedField") for error in report["errors"])
    with pytest.raises(ValueError, match="unexpectedField"):
        compile_runtime_program(document)
    assert document == frozen


def test_native_visibility_requires_an_explicit_choice():
    document, params = authored()
    del params["hideUseGraphic"]
    report = validate_runtime_program(document)
    assert not report["ok"]
    assert any(error["code"] == "shape_required"
               and error["path"].endswith(".params.hideUseGraphic") for error in report["errors"])


@pytest.mark.parametrize("value", [None, "true", 1, {}, []])
def test_native_visibility_requires_boolean(value):
    document, params = authored()
    params["hideUseGraphic"] = value
    assert not validate_runtime_program(document)["ok"]
