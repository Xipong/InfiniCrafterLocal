"""Certified native geometry semantics for model context, never gameplay lowering.

These are engine-helper contracts, not weapon/AI presets. Both native method
certificates and the complete captured helper graph must match. New modules,
modified observations and unknown helpers retain their original source graph.
The raw capture is never mutated. Native equivalence witnesses live in
EngineRuntimeChecks.NativeAttackGeometryOracle.cs.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

_MODULE = "033e87cd-cefe-4dc6-a1fb-e14aa938bbb2"
_CERTIFICATES = {
    "IntersectsConeSlowMoreAccurate": "c85829078c4bccf530fe68212562d7b6e048c887da065d6ce5a0eedf5aca06d4",
    "DoesFitInCone": "2d33905dcbb4bdaddc0a305cdc6d34208219f11a582879b5a2d21090be564631",
    "ToRotationVector2": "64fa8c3bc1e89e9930f07b73dcc88c78a6e4cfac5675b69a18d7624d3197d7ca",
    "ClosestPointInRect": "d535f4dcef32567b9a7aed84aaf0e1690051a92901c1ca557225fa8a5b9aa161",
    "TopLeft": "4c5524e6dd4e6069912d2788be39d406fce5416b276717b2357b9ea678c7ede2",
    "TopRight": "8822e75ab56066ffa0a83487b8a22a60d477182a11a65efbf2964d45a969e98f",
    "BottomLeft": "5391b8b37b986395ca292be57f77f039a1d8f42ceeb19b292bb0049846c24e07",
    "BottomRight": "5fb7a22f61b7a57d8d53ab85c29e7914ca6c643ab9cbab5caa75d4dbe6a7aa00",
    "RotatedBy": "c5bee5294ff830da357e4ec3691d3cba4e80975b5fbe91dd20f1bb7247cde290",
    "ToRotation": "0a5bbc10f474a07dca1edd9352fe88b17c26097a0fa82678a0a199e36a17dc9d",
}
_GRAPH_HASHES = {
    "IntersectsConeSlowMoreAccurate": "400646b36b6b805d43f88baf68ea91d5a01373b04cb6c32a91010d3a6796e415",
    "DoesFitInCone": "6dc1cb5b80177a86595e6a36616b899951c9ad2b0268790a17c1281ad85d69fe",
}
_POINT_DEPENDENCIES = {"DoesFitInCone", "RotatedBy", "ToRotation"}
_RECT_DEPENDENCIES = set(_CERTIFICATES)


def _certificate_present(roster: list, name: str) -> bool:
    rows = [row for row in roster if isinstance(row, dict) and row.get("method") == "Terraria.Utils." + name]
    return len(rows) == 1 and rows[0] == {
        "method": "Terraria.Utils." + name, "sourceModuleVersionId": _MODULE,
        "sourceMethodSha256": _CERTIFICATES[name],
    }


def _rule(name: str) -> dict:
    if name == "DoesFitInCone":
        return {
            "kind": "point_in_native_cone",
            "inputs": ["point", "coneCenter", "coneLength", "coneRotation", "maximumAngle"],
            "offset": "point - coneCenter",
            "angle": "atan2(rotate(offset, 0f - coneRotation).y, rotate(offset, 0f - coneRotation).x)",
            "accept": "NOT(angle < -maximumAngle OR angle > maximumAngle) AND length(offset) < coneLength",
            "boundaries": "Angular edges included; radial edge excluded. Angles are radians; lengths are world pixels.",
            "numeric": "Native float/vector operations and RotatedBy(double) rounding/zero-origin addition (including signed zero) apply. Unordered angle comparisons do not reject; unordered distance comparison rejects. Not abs(angle)<=maximumAngle for NaN inputs.",
        }
    return {
        "kind": "native_five_point_rectangle_cone_test",
        "inputs": ["targetRect", "coneCenter", "coneLength", "coneRotation", "maximumAngle"],
        "forwardTip": "coneCenter + (cos(coneRotation), sin(coneRotation)) * coneLength",
        "orderedPoints": ["closestPointInRect(targetRect,forwardTip)", "targetRect.topLeft", "targetRect.topRight",
                          "targetRect.bottomLeft", "targetRect.bottomRight"],
        "accept": "ANY ordered point satisfies DoesFitInCone(point, coneCenter, coneLength, coneRotation, maximumAngle); stop at first true",
        "rectangleEdges": "right=x+width; bottom=y+height (not width-1/height-1). Closest point clamps each tip coordinate: first replace values > right/bottom with that edge, then values < left/top with that edge; NaN stays NaN.",
        "scope": "This particular five-point native test, NOT a general exact rectangle/cone intersection, center-only test, or circle/AABB test. Native float rounding applies.",
    }


def project_collision_behavior(reference: dict[str, Any]) -> dict[str, Any]:
    """Return a detached reference with only certified helper bodies simplified."""
    out = copy.deepcopy(reference)
    if (reference.get("source") != "read_only_native_attack_source" or type(reference.get("version")) is not int
            or reference["version"] != 1 or not isinstance(reference.get("sourceMethods"), list)):
        return out
    collision = out.get("collision")
    if not isinstance(collision, dict) or not isinstance(collision.get("predicateSources"), list):
        return out
    roster = reference["sourceMethods"]
    for index, program in enumerate(collision["predicateSources"]):
        if not isinstance(program, dict):
            continue
        name = program.get("method", "").removeprefix("Terraria.Utils.") if isinstance(program.get("method"), str) else ""
        if name not in _GRAPH_HASHES or program.get("method") != "Terraria.Utils." + name:
            continue
        try:
            digest = hashlib.sha256(json.dumps(program, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        except (TypeError, ValueError):
            continue
        dependencies = _POINT_DEPENDENCIES if name == "DoesFitInCone" else _RECT_DEPENDENCIES
        if digest != _GRAPH_HASHES[name] or not all(_certificate_present(roster, dep) for dep in dependencies):
            continue
        collision["predicateSources"][index] = {"method": program["method"], "geometryRule": _rule(name)}
    return out
