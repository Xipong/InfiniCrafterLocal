"""Helper semantics admission; numeric equivalence is executed against tML in the native check."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.pipelines.context.attack_geometry import project_collision_behavior


def reference():
    parent = json.loads((Path(__file__).parent / "fixtures/native_excalibur_parent_capture.json").read_text())
    return parent["directProjectileRaw"]["attackReference"]


def test_certified_helpers_become_geometry_rules_without_changing_call_conditions():
    raw = reference()
    before = copy.deepcopy(raw)
    result = project_collision_behavior(raw)
    rectangle, point = result["collision"]["predicateSources"]
    assert rectangle["geometryRule"]["kind"] == "native_five_point_rectangle_cone_test"
    assert point["geometryRule"]["kind"] == "point_in_native_cone"
    assert rectangle["geometryRule"]["orderedPoints"] == [
        "closestPointInRect(targetRect,forwardTip)", "targetRect.topLeft", "targetRect.topRight",
        "targetRect.bottomLeft", "targetRect.bottomRight",
    ]
    assert point["geometryRule"]["accept"] == "NOT(angle < -maximumAngle OR angle > maximumAngle) AND length(offset) < coneLength"
    for key in raw["collision"]:
        if key != "predicateSources":
            assert result["collision"][key] == raw["collision"][key]
    assert raw == before
    assert project_collision_behavior(result) == result
    assert len(json.dumps(result)) < len(json.dumps(raw))


@pytest.mark.parametrize("mutation", ["unknown_method", "extra_field", "comparison", "module", "method_hash", "missing_dependency", "changed_dependency", "duplicate_certificate"])
def test_unknown_or_changed_helper_contract_is_not_summarized(mutation):
    raw = reference()
    if mutation == "unknown_method":
        raw["collision"]["predicateSources"][0]["method"] += "V2"
    elif mutation == "extra_field":
        raw["collision"]["predicateSources"][0]["futureBehavior"] = {"new": True}
    elif mutation == "comparison":
        raw["collision"]["predicateSources"][0]["predicates"][0]["op"] = "brtrue.s"
    elif mutation in {"module", "method_hash"}:
        key = "sourceModuleVersionId" if mutation == "module" else "sourceMethodSha256"
        raw["collision"]["predicateSources"][0][key] = "unknown"
    else:
        target = next(row for row in raw["sourceMethods"] if row["method"] == "Terraria.Utils.ClosestPointInRect")
        if mutation == "missing_dependency":
            raw["sourceMethods"].remove(target)
        elif mutation == "changed_dependency":
            target["sourceMethodSha256"] = "different"
        else:
            raw["sourceMethods"].append(copy.deepcopy(target))
    result = project_collision_behavior(raw)
    assert result["collision"]["predicateSources"][0] == raw["collision"]["predicateSources"][0]


def test_geometry_contract_is_generic_not_projectile_identity_routing():
    raw = reference()
    expected = project_collision_behavior(raw)["collision"]["predicateSources"]
    raw["identityPredicates"] = {"Projectile.type": 12345, "Projectile.aiStyle": -900}
    assert project_collision_behavior(raw)["collision"]["predicateSources"] == expected
    raw["version"] = 2
    assert project_collision_behavior(raw) == raw


def test_point_certificate_refusal_does_not_erase_unknown_mechanics():
    raw = reference()
    raw["collision"]["predicateSources"][1]["observations"][1]["expression"] = "ret(cgt(distance,coneLength))"
    assert project_collision_behavior(raw)["collision"]["predicateSources"][1] == raw["collision"]["predicateSources"][1]
