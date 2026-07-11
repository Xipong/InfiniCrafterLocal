from __future__ import annotations

import dataclasses
import json

from infini_local.core.balance_report import BALANCE_REPORT_SCHEMA_VERSION, build_balance_report
from infini_local.core.result_types import BalanceReportModel, ClampRecord, RepairResult, RuntimeCompileResult


def test_internal_result_records_round_trip_and_remain_immutable() -> None:
    clamp = ClampRecord(
        field="damage", raw=9999, final=60, kind="balance",
        reason="authored_damage_soft_envelope", source="set_item_stats",
    )
    assert clamp.to_dict() == {
        "field": "damage", "raw": 9999, "final": 60, "kind": "balance",
        "reason": "authored_damage_soft_envelope", "source": "set_item_stats",
    }
    try:
        clamp.raw = 5
        raise AssertionError("ClampRecord must stay frozen")
    except dataclasses.FrozenInstanceError:
        pass

    with_extra = ClampRecord(field="x", raw=1, final=1, kind="safety", reason="t", extra={"k": 1})
    assert with_extra.to_dict()["extra"] == {"k": 1}

    repair = RepairResult(
        kind="retry_attempted", attempted=True, accepted=False,
        rejected_fields=("damage",), reason="targeted_retry",
    ).to_dict()
    assert repair["rejectedFields"] == ["damage"]
    assert repair["attempted"] is True and repair["accepted"] is False

    compiled = RuntimeCompileResult(patch={"damage": 10}, provenance={}, errors=[])
    failed = RuntimeCompileResult(patch={}, provenance={}, errors=[{"field": "damage"}])
    assert compiled.ok is True and failed.ok is False
    assert failed.to_dict()["provenanceSource"] == "runtime_plan_provenance_report"


def test_balance_report_model_round_trips_real_and_empty_reports() -> None:
    data = {
        "gameplay": {"damage": 40, "useTime": 15, "rarity": "pre_boss"},
        "debug": {"statProfile": {"bucket": "pre_boss", "sourceMaxDamage": 30, "sourceFastestUseTime": 10}},
    }
    model = BalanceReportModel.from_report_dict(build_balance_report(data))
    assert model.schema == BALANCE_REPORT_SCHEMA_VERSION
    assert "powerBand" in model.power_band
    assert model.authored or model.final
    assert json.loads(json.dumps(model.to_dict(), default=str))

    empty = BalanceReportModel().to_dict()
    assert empty["schema"] == "infini.balance-report.v1"
    assert empty["clamps"] == {} and empty["repair"] == {}
