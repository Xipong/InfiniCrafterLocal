"""Source-policy controls; these do not claim native motion execution coverage."""
from __future__ import annotations

from dataclasses import replace

import pytest

from infini_local.core.runtime_authoring.capability_registry import PROJECTILE_MODIFIER_COMPONENTS
from infini_local.qa import primitive_loss_audit as audit


def test_current_motion_dto_surface_has_source_and_strict_wire_owners():
    structural = audit.structural_surface_audit()
    assert structural["ok"], structural
    components = audit.runtime_component_surface_audit()
    assert components["ok"], components
    assert "RuntimeSeekSpec" in components["unclassifiedByClass"]
    assert "RuntimeMotionWindowSpec" in components["unclassifiedByClass"]
    assert "RuntimeWindowedMotionSpec" in components["unclassifiedByClass"]
    assert components["componentClasses"].keys() == set(PROJECTILE_MODIFIER_COMPONENTS.values())
    # No serialized writable class in the new source may escape classification.
    motion = (audit._MODEL_ROOT / "Common/Models/Contracts/RuntimeMotionComponents.cs").read_bytes()
    classes, _ = audit._dto_component_types(motion)
    assert {name for name, fields in classes.items() if fields} - {"RuntimeEntitySpec"} <= components["unclassifiedByClass"].keys()


@pytest.fixture(scope="module")
def dto():
    return audit._runtime_dto_source()


def add_property(dto, cls, declaration=b"public float UnexposedFutureField { get; set; }"):
    tree = audit._PARSER.parse(dto).root_node
    node = next(row for row in audit._nodes(tree, "class_declaration")
                if row.child_by_field_name("name").text.decode() == cls)
    position = node.child_by_field_name("body").start_byte + 1
    return dto[:position] + b"\n" + declaration + b"\n" + dto[position:]


@pytest.fixture(scope="module")
def component_classes(dto):
    return audit.runtime_component_surface_audit(dto)["componentClasses"]


@pytest.mark.parametrize("member", tuple(PROJECTILE_MODIFIER_COMPONENTS.values()))
def test_every_component_rejects_an_unexposed_future_field(dto, component_classes, member):
    cls = component_classes[member]
    report = audit.runtime_component_surface_audit(add_property(dto, cls))
    assert not report["ok"], report
    assert report["unclassifiedByClass"][cls] == ["UnexposedFutureField"]
    assert "UnexposedFutureField" in report["wireDtoDriftByClass"][cls]


@pytest.mark.parametrize("cls", ("RuntimeMotionWindowSpec", "RuntimeWindowedMotionSpec", "RuntimeTimedModifierSpec"))
def test_shared_and_inherited_window_reject_unexposed_future_field(dto, cls):
    report = audit.runtime_component_surface_audit(add_property(dto, cls))
    assert not report["ok"], report
    assert report["unclassifiedByClass"][cls] == ["UnexposedFutureField"]
    if cls == "RuntimeWindowedMotionSpec":
        assert "UnexposedFutureField" in report["unclassifiedByClass"]["RuntimeSeekSpec"]
    if cls == "RuntimeTimedModifierSpec":
        for concrete in ("RuntimeTurnModifierSpec", "RuntimeSpeedModifierSpec", "RuntimeHomingModifierSpec", "RuntimeNpcAttractionSpec"):
            assert "UnexposedFutureField" in report["unclassifiedByClass"][concrete]


def test_timing_base_inventory_uses_inheritance_not_a_base_name_whitelist(dto):
    report = audit.runtime_component_surface_audit(dto.replace(b"RuntimeTimedModifierSpec", b"RelocatedTimingBase"))
    assert report["ok"], report
    assert "RelocatedTimingBase" in report["unclassifiedByClass"]


def test_missing_inherited_timing_leaf_is_not_hidden_by_other_classes(dto):
    declaration = next(row for row in audit._nodes(audit._PARSER.parse(dto).root_node, "class_declaration")
                       if row.child_by_field_name("name").text == b"RuntimeTimedModifierSpec")
    prop = next(row for row in declaration.child_by_field_name("body").named_children
                if row.type == "property_declaration" and row.child_by_field_name("name").text == b"StartDelayTicks")
    name = prop.child_by_field_name("name")
    source = dto[:name.start_byte] + b"RemovedDelayTicks" + dto[name.end_byte:]
    with pytest.raises(ValueError, match="RuntimeTurnModifierSpec.*StartDelayTicks"):
        audit.runtime_component_surface_audit(source)


@pytest.mark.parametrize("mutation", ("missing", "unknown"))
def test_dynamic_entity_wire_keys_remain_exact(monkeypatch, mutation):
    import infini_local.core.runtime_authoring.wire_validator as wire

    keys = wire._ENTITY_KEYS - {"seek"} if mutation == "missing" else wire._ENTITY_KEYS | {"futureComponent"}
    monkeypatch.setattr(wire, "_ENTITY_KEYS", keys)
    report = audit.structural_surface_audit()
    assert not report["ok"], report
    assert report["wireDtoDriftByClass"]["RuntimeEntitySpec"] == ["Seek" if mutation == "missing" else "FutureComponent"]


def test_entity_root_still_rejects_unknown_writable_fields(dto):
    report = audit.structural_surface_audit(add_property(dto, "RuntimeEntitySpec"))
    assert not report["ok"], report
    assert report["unclassifiedByClass"]["RuntimeEntitySpec"] == ["UnexposedFutureField"]


def test_component_binding_is_read_from_csharp_not_a_class_name_table(dto):
    report = audit.runtime_component_surface_audit(dto.replace(b"RuntimeSeekSpec", b"RelocatedSeekSpec"))
    assert report["ok"], report
    assert report["componentClasses"]["seek"] == "RelocatedSeekSpec"


def test_partial_property_inventory_ignores_nested_class_and_decoys():
    dto = b'''partial class MovedDto {
        public int First { get; set; }
        class Nested { public int Foreign { get; set; } }
        // public int Comment { get; set; }
        const string Text = "public int String { get; set; }";
    }
    partial class MovedDto {
        public int Second { get; init; }
        [JsonIgnore] public bool Computed => true;
    }'''
    assert audit._class_properties(dto, "MovedDto") == {"First", "Second"}


def test_missing_nested_wire_key_is_detected_from_registry_projection(dto, monkeypatch):
    cap = audit.CAPABILITY_REGISTRY["seek_projectile"]
    params = {name: spec for name, spec in cap.params.items() if "maxSpeed" not in spec.wire_field_names(name)}
    monkeypatch.setattr(audit, "CAPABILITY_REGISTRY", {**audit.CAPABILITY_REGISTRY,
        cap.name: replace(cap, params=params)})
    report = audit.runtime_component_surface_audit(dto)
    assert not report["ok"], report
    assert report["wireDtoDriftByClass"]["RuntimeSeekSpec"] == ["MaxSpeed"]


def test_one_component_cannot_lose_shared_window_wire_leaf(dto, monkeypatch):
    cap = audit.CAPABILITY_REGISTRY["seek_projectile"]
    window = cap.params["window"]
    alternatives = tuple(replace(variant, properties={name: spec for name, spec in variant.properties.items()
                                                     if "window.clock" not in spec.wire_field_names(name)})
                         for variant in window.alternatives)
    params = {**cap.params, "window": replace(window, alternatives=alternatives)}
    monkeypatch.setattr(audit, "CAPABILITY_REGISTRY", {**audit.CAPABILITY_REGISTRY,
        cap.name: replace(cap, params=params)})
    report = audit.runtime_component_surface_audit(dto)
    assert not report["ok"], report
    assert report["wireDtoDriftByClass"]["RuntimeMotionWindowSpec"] == ["Clock"]


@pytest.mark.parametrize("fn,cls,field", (
    ("set_projectile_arrival", "RuntimeArrivalSpec", "Action"),
    ("sustain_projectile_mana", "RuntimeManaSustainSpec", "Cadence"),
))
def test_fn_selected_literals_are_owned_not_hidden(dto, monkeypatch, fn, cls, field):
    cap = audit.CAPABILITY_REGISTRY[fn]
    assert field[0].lower() + field[1:] in cap.fixed_wire_literals
    monkeypatch.setattr(audit, "CAPABILITY_REGISTRY", {**audit.CAPABILITY_REGISTRY,
        fn: replace(cap, fixed_wire_literals={})})
    report = audit.runtime_component_surface_audit(dto)
    assert not report["ok"], report
    assert report["wireDtoDriftByClass"][cls] == [field]
