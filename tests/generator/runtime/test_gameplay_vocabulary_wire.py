"""Current gameplay vocabulary projects to exact native identities and domains."""
import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness

_ADDED_CAPABILITIES = frozenset({"reduce_heal_cooldown_on_event", "place_object"})


@pytest.mark.parametrize("value", [0, 1, 128, 255])
def test_transparency_byte_is_exact_existing_native_domain(value):
    source = build_capability_witness("set_opacity")
    call = next(call for call in source["runtimeProgram"]["calls"] if call["fn"] == "set_opacity")
    call["params"]["transparencyByte"] = value
    wire = compile_runtime_program(source)
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    assert entity["opacity"]["alpha"] == value
    call["params"]["alpha"] = call["params"].pop("transparencyByte")
    assert not validate_runtime_program(source)["ok"]


def test_common_combat_names_have_explicit_units_without_changing_numeric_projection():
    cap = CAPABILITY_REGISTRY["generated_buff_on_use"]
    card = cap.author_prompt_card()["params"]["combat"]["properties"]
    for key, units, old in (("attackSpeedBonus", "additive_percent", "attackSpeedPercent"),
                            ("critChance", "percentage_points", "critChancePoints"),
                            ("damageBonus", "additive_percent", "damagePercent")):
        spec = cap.params["combat"].properties[key]
        assert card[key]["units"] == units
        assert spec.wire_name == "combat." + old
        for value in (spec.minimum, 0, spec.maximum):
            assert spec.to_wire(value) == value
        assert old not in card


@pytest.mark.parametrize("name", sorted(_ADDED_CAPABILITIES))
def test_placement_and_cooldown_have_current_executable_witness(name):
    from infini_local.qa.capability_witnesses import build_capability_witness
    source = build_capability_witness(name)
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    assert validate_runtime_wire(wire)["ok"]
    if name == "place_object":
        placement = next(binding["usePolicy"]["action"]["placement"]
                         for binding in wire["runtimeProgram"]["bindings"]
                         if binding["usePolicy"]["action"]["kind"] == "place_item")
        assert placement["tileId"] == placement["wallId"] == -1
        assert placement["ownedTile"] == next(call["params"] for call in source["runtimeProgram"]["calls"]
                                              if call["fn"] == "place_object")
        assert "placedBody" in placement
    else:
        assert any(event["actionCode"] == 12 and event["cooldownReductionTicks"] > 0
                   for entity in wire["runtimeProgram"]["entities"] for event in entity.get("events", []))
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
        authored_document=source, final_document=wire)["ok"]
