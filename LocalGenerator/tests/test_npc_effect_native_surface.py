"""Read-only native-source audits: no native build or game execution."""
from dataclasses import replace

import pytest

from infini_local.qa import primitive_loss_audit as audit
from infini_local.qa.capability_library_audit import _runtime_param_bound_rows

FN = "apply_npc_effect_on_event"
CLS = "RuntimeNpcEffectSpec"


def test_npc_component_has_per_destination_source_and_wire_coverage():
    report = audit.runtime_component_surface_audit()
    assert report["ok"], report
    assert CLS in report["unclassifiedByClass"]
    rows = {r["param"]: r for r in _runtime_param_bound_rows() if r["capability"] == FN}
    for name in ("damagePerSecond", "defenseDelta", "contactDamageMultiplier", "velocityRetentionPerTick", "chancePercent"):
        assert rows[name]["csharpClass"] == CLS
        assert rows[name]["preserved"], rows[name]
        assert rows[name]["admission"] == "reject_without_clamp"


def test_unexposed_native_npc_property_is_not_hidden():
    dto = audit._runtime_dto_source()
    marker = b"public sealed class RuntimeNpcEffectSpec\n{"
    assert marker in dto
    altered = dto.replace(marker, marker + b"\npublic float FutureField { get; set; }", 1)
    report = audit.runtime_component_surface_audit(altered)
    assert not report["ok"]
    assert report["unclassifiedByClass"][CLS] == ["FutureField"]
    assert report["wireDtoDriftByClass"][CLS] == ["FutureField"]


def test_missing_npc_wire_leaf_is_detected_per_capability(monkeypatch):
    cap = audit.CAPABILITY_REGISTRY[FN]
    broken = replace(cap, params={name: spec for name, spec in cap.params.items() if name != "chancePercent"})
    monkeypatch.setattr(audit, "CAPABILITY_REGISTRY", {**audit.CAPABILITY_REGISTRY, FN: broken})
    report = audit.runtime_component_surface_audit()
    assert not report["ok"]
    assert report["wireDtoDriftByClass"][CLS] == ["Chance"]


@pytest.mark.parametrize("field,bounds", [("LifeRegenPenalty", [0, 400]), ("DefenseDelta", [-100, 100]),
    ("ContactDamageMultiplier", [0.1, 3]), ("VelocityRetentionPerTick", [0.1, 1]), ("Chance", [0, 1])])
def test_native_reject_bounds_are_observed_from_actual_setter(field, bounds):
    dto = audit._runtime_dto_source()
    assert audit.number_rejection_bounds(dto, CLS, field) == bounds


def test_nonfinite_or_wrong_backing_guard_cannot_claim_rejection_bounds():
    dto = audit._runtime_dto_source()
    assert audit.number_rejection_bounds(dto.replace(b"float.IsFinite(value) &&", b"true &&"), CLS, "Chance") is None
    assert audit.number_rejection_bounds(dto.replace(b"set => _chance = Require", b"set => _defenseDelta = Require"), CLS, "Chance") is None
