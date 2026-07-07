"""Stage 3 typed internal results groundwork — result_types dataclasses."""
from __future__ import annotations

import json
from infini_local.core.result_types import (
    ClampRecord,
    RepairResult,
    RuntimeCompileResult,
    BalanceReportModel,
)
from infini_local.core.balance_report import build_balance_report, BALANCE_REPORT_SCHEMA_VERSION


def test_clamp_record_roundtrip():
    r = ClampRecord(
        field="damage", raw=9999, final=60, kind="balance",
        reason="authored_damage_soft_envelope", source="set_item_stats",
    )
    d = r.to_dict()
    assert d["field"] == "damage"
    assert d["raw"] == 9999 and d["final"] == 60
    assert d["kind"] == "balance"
    assert d["reason"] == "authored_damage_soft_envelope"
    assert d["source"] == "set_item_stats"
    assert "extra" not in d
    # frozen and immutable
    import dataclasses
    try:
        r.raw = 5
        assert False, "should be frozen"
    except dataclasses.FrozenInstanceError:
        pass


def test_clamp_record_extra_optional():
    r = ClampRecord(field="x", raw=1, final=1, kind="safety", reason="t", extra={"k": 1})
    d = r.to_dict()
    assert d["extra"] == {"k": 1}


def test_repair_result_shape():
    r = RepairResult(kind="retry_attempted", attempted=True, accepted=False, rejected_fields=("damage",),
                     reason="targeted_retry")
    d = r.to_dict()
    assert d["kind"] == "retry_attempted"
    assert d["attempted"] is True and d["accepted"] is False
    assert d["rejectedFields"] == ["damage"]
    assert d["reason"] == "targeted_retry"


def test_runtime_compile_result_ok_flag():
    r = RuntimeCompileResult(patch={"damage": 10}, provenance={}, errors=[])
    assert r.ok is True
    r2 = RuntimeCompileResult(patch={}, provenance={}, errors=[{"field": "damage"}])
    assert r2.ok is False
    d = r2.to_dict()
    assert d["errors"] == [{"field": "damage"}]
    assert d["provenanceSource"] == "runtime_plan_provenance_report"


def test_balance_report_model_from_real_report():
    data = {
        "gameplay": {"damage": 40, "useTime": 15, "rarity": "pre_boss"},
        "debug": {"statProfile": {"bucket": "pre_boss", "sourceMaxDamage": 30, "sourceFastestUseTime": 10}},
    }
    report = build_balance_report(data)
    model = BalanceReportModel.from_report_dict(report)
    assert model.schema == BALANCE_REPORT_SCHEMA_VERSION
    assert "powerBand" in model.power_band
    assert model.authored or model.final  # at least one populated
    d = model.to_dict()
    assert d["schema"] == model.schema
    assert json.loads(json.dumps(d, default=str))  # serializable


def test_balance_report_model_empty_roundtrip():
    m = BalanceReportModel()
    d = m.to_dict()
    assert d["schema"] == "infini.balance-report.v1"
    assert d["clamps"] == {} and d["repair"] == {}
