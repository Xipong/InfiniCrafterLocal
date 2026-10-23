"""Explicit contact shape survives authoring, receipts, delivery and rejection."""
from copy import deepcopy
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts


def test_contact_geometry_delivery_and_strict_boundary():
    fn = "set_projectile_contact_geometry"
    for shape in ("ellipse", "rectangle", "capsule"):
        doc = build_capability_witness(fn)
        call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
        call["params"] = dict(shape=shape, lengthPx=80, widthPx=18, orientation="velocity", angleRadians=.5)
        wire = compile_runtime_program(doc)
        entity = next(e for e in wire["runtimeProgram"]["entities"] if "contactGeometry" in e)
        assert entity["contactGeometry"] == call["params"]
        assert validate_runtime_wire(wire)["ok"]
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=doc, final_document=wire)["ok"]
        for key, value in (("shape", "sprite"), ("widthPx", None), ("lengthPx", 1025), ("angleRadians", float("nan"))):
            broken = deepcopy(wire); broken.pop("runtimeContract")
            next(e for e in broken["runtimeProgram"]["entities"] if "contactGeometry" in e)["contactGeometry"][key] = value
            assert not validate_runtime_wire(broken)["ok"]
        call["params"]["orientation"] = "sprite"
        assert not validate_runtime_program(doc)["ok"]
