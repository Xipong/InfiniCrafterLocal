"""Structured Author parameters keep strict shape and exact wire provenance."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import MappingProxyType

import pytest

from infini_local.core.runtime_authoring import capability_registry as registry
from infini_local.core.runtime_authoring import compiler, technical_lowering
from infini_local.core.runtime_authoring.capability_registry import ParamSpec
from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
from infini_local.qa.capability_witnesses import build_capability_witness


def _typed_collision(monkeypatch):
    """Use an existing executable component to prove the generic seam."""
    document = build_capability_witness("set_projectile_collision")
    cap = registry.CAPABILITY_REGISTRY["set_projectile_collision"]
    params = dict(cap.params)
    params.pop("npcImmunityMode", None)
    cooldown = cap.retained_receipt_params["localNpcHitCooldownEngineUnits"]
    params["immunity"] = ParamSpec(
        "union", "Exact immunity variant", alternatives=(
            ParamSpec("string", "Owner immunity", enum=("owner_shared",),
                      wire_literals=MappingProxyType({"npcImmunityMode": "owner", "localNpcHitCooldownTicks": -1})),
            ParamSpec("object", "Local cooldown", properties=MappingProxyType({
                "localCooldown": replace(cooldown, minimum=0),
            }), wire_literals=MappingProxyType({"npcImmunityMode": "local"})),
        ),
    )
    modified = dict(registry.CAPABILITY_REGISTRY)
    changed = replace(cap, params=MappingProxyType(params), retained_receipt_params=cap.retained_receipt_params)
    modified[cap.name] = replace(changed, final_wire_paths=registry._exact_wire_paths(changed))
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", modified)
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call["params"].pop("npcImmunityMode", None)
    call["params"].pop("localNpcHitCooldownEngineUnits", None)
    return document, call


@pytest.mark.parametrize("value, mode, cooldown", [
    ("owner_shared", "owner", -1), ({"localCooldown": 0}, "local", 0),
    ({"localCooldown": 37}, "local", 37), ({"localCooldown": 600}, "local", 600),
])
def test_structured_param_compiles_existing_wire_and_exact_receipts(monkeypatch, value, mode, cooldown):
    document, call = _typed_collision(monkeypatch)
    call["params"]["immunity"] = value
    compiled = compiler.compile_runtime_program(document)
    entity = next(e for e in compiled["runtimeProgram"]["entities"] if e["id"] == call["target"])
    assert entity["collision"]["npcImmunityMode"] == mode
    assert entity["collision"]["localNpcHitCooldownTicks"] == cooldown
    receipts = compiled["runtimeContract"]["finalWireReceipts"]
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=compiled)["ok"]
    relevant = [r for r in receipts if ".params.immunity" in r.get("authoredPath", "")]
    assert len(relevant) == 2
    for removed in relevant:
        assert not technical_lowering.audit_compiler_receipts(
            [r for r in receipts if r is not removed], authored_document=document, final_document=compiled,
        )["ok"]
    forged = deepcopy(receipts)
    next(r for r in forged if r.get("authoredPath") == relevant[0]["authoredPath"])["value"] = "forged"
    assert not technical_lowering.audit_compiler_receipts(forged, authored_document=document, final_document=compiled)["ok"]


@pytest.mark.parametrize("invalid", [None, "local", {}, {"localCooldown": -1},
                                      {"localCooldown": 601}, {"localCooldown": True},
                                      {"localCooldown": 10, "owner": True}])
def test_structured_param_rejects_missing_or_invalid_choice(monkeypatch, invalid):
    document, call = _typed_collision(monkeypatch)
    call["params"]["immunity"] = invalid
    with pytest.raises(ValueError):
        compiler.compile_runtime_program(document)


def test_object_keeps_exact_leaf_units_and_rejects_empty_group():
    spec = ParamSpec("object", "Explicit grouped stats", min_properties=1, properties={
        "radiusTiles": ParamSpec("number", "Radius on the exact pixel lattice", minimum=0.5,
                                 maximum=48, multiple_of=1 / 16, wire_multiplier=16, wire_name="radiusPx"),
        "updatesPerTick": ParamSpec("integer", "Updates", minimum=1, maximum=6, wire_offset=-1,
                                    wire_name="extraUpdates", required=False),
    })
    assert not strict_schema_errors({"radiusTiles": 8.0625, "updatesPerTick": 6}, spec.schema())
    rows = spec.projected_fields({"radiusTiles": 8.0625, "updatesPerTick": 6}, "group")
    assert [(r.authored_path, r.wire_path, r.value) for r in rows] == [
        ("group.radiusTiles", "radiusPx", 129), ("group.updatesPerTick", "extraUpdates", 5),
    ]
    assert strict_schema_errors({}, spec.schema())
    assert strict_schema_errors({"radiusTiles": 0.6}, spec.schema())


def test_ambiguous_union_fails_closed():
    spec = ParamSpec("union", "Invalid duplicate branches", alternatives=(
        ParamSpec("string", "One", enum=("x",), wire_literals={"field": 1}),
        ParamSpec("string", "Two", enum=("x",), wire_literals={"field": 2}),
    ))
    with pytest.raises(ValueError, match="exactly one"):
        spec.projected_fields("x", "choice")


def test_nested_union_diagnostic_does_not_unfreeze_the_valid_sibling(monkeypatch):
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, validate_runtime_program
    document, call = _typed_collision(monkeypatch)
    call["params"]["immunity"] = {"localCooldown": 601}
    report = validate_runtime_program(document)
    assert not report["ok"]
    leaf = next(e for e in report["errors"] if e["path"].endswith(".immunity.localCooldown"))
    assert leaf["code"] == "shape_maximum"
    scope = build_runtime_repair_scope(document, report["errors"])
    permissions = next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == "witness_call")
    assert "params.immunity.localCooldown" in permissions
    assert "params.immunity" not in permissions
    assert "params" not in permissions


def test_retained_provenance_preserves_old_wire_without_accepting_old_author(monkeypatch):
    old_author = build_capability_witness("set_projectile_collision")
    corpus = json.loads((Path(__file__).with_name("fixtures") / "projectile_retained_wire.json").read_text())
    old_wire = next(row["wire"] for row in corpus["cases"] if row["fn"] == "set_projectile_collision")
    old_call = next(c for c in old_author["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    old_call["params"].pop("immunity")
    old_call["params"].pop("updatesPerTick")
    old_call["params"].update(npcImmunityMode="owner", localNpcHitCooldownEngineUnits=37, extraUpdates=5)
    old_receipts = deepcopy(old_wire["runtimeContract"]["finalWireReceipts"])
    _typed_collision(monkeypatch)
    assert technical_lowering.audit_compiler_receipts(old_receipts, final_document=old_wire)["ok"]
    assert not technical_lowering.audit_compiler_receipts(
        old_receipts, authored_document=old_author, final_document=old_wire,
    )["ok"]
    with pytest.raises(ValueError):
        compiler.compile_runtime_program(old_author)
    changed = deepcopy(old_receipts)
    row = next(r for r in changed if r.get("authoredPath", "").endswith(".localNpcHitCooldownEngineUnits"))
    row["value"] = 10.5
    assert not technical_lowering.audit_compiler_receipts(changed)["ok"]
    row["value"] = 10
    row["authoredPath"] = row["authoredPath"].replace("localNpcHitCooldownEngineUnits", "unregisteredOldName")
    assert not technical_lowering.audit_compiler_receipts(changed)["ok"]


def test_fn_literal_provenance_requires_value_source_and_complete_coverage(monkeypatch):
    document = build_capability_witness("configure_spawn")
    changed = dict(registry.CAPABILITY_REGISTRY)
    changed["configure_spawn"] = replace(changed["configure_spawn"], fixed_wire_literals={"enabled": True})
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", changed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    literal = next(r for r in receipts if r.get("fn") == "configure_spawn" and r["finalPath"].endswith(".enabled"))
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    for key, value in (("value", False), ("status", "delivered"), ("authoredPath", "runtimeProgram.calls[0].fn")):
        forged = deepcopy(receipts)
        forged[receipts.index(literal)][key] = value
        assert not technical_lowering.audit_compiler_receipts(forged, authored_document=document, final_document=wire)["ok"]
    assert not technical_lowering.audit_compiler_receipts([r for r in receipts if r is not literal], final_document=wire)["ok"]
