"""Retained native input contracts; behavior lives in EngineRuntimeChecks.TooltipSecondaries."""
import copy
import json
from pathlib import Path

from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


def test_played_secondary_native_inputs_preserve_exact_typed_events():
    root = Path(__file__).resolve().parents[2]
    rows = json.loads((root / "tools/fixtures/played-secondaries-delivered.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {"g_4a1c8253fd834bff", "g_232a7838dccbe91d"}
    before = copy.deepcopy(rows)
    for row in rows:
        report = validate_runtime_wire(row)
        assert not report["ok"] and any(e["path"] == "$.runtimeProgram.itemUse.releaseTiming" for e in report["errors"])
        control = copy.deepcopy(row)
        assert control["gameplay"].pop("releaseTiming") == "immediate"
        assert control["runtimeProgram"]["itemUse"].pop("releaseTiming") == "immediate"
        assert control["runtimeProgram"]["itemUse"]["hideUseGraphic"] is True
        assert validate_runtime_wire(control)["ok"]
        assert control["runtimeProgram"]["entities"] == row["runtimeProgram"]["entities"]
    stone = by_id["g_4a1c8253fd834bff"]["runtimeProgram"]
    source = next(e for e in stone["entities"] if e["id"] == stone["primaryEntityId"])
    assert source["damage"]["damage"] == 10
    assert source["events"] == [dict(action="damage_area_on_event", actionCode=3,
        damageMultiplier=.5, delayTicks=10, event="on_hit", id="stonegel_delayed_splash", radiusPx=24)]
    ebon = by_id["g_232a7838dccbe91d"]["runtimeProgram"]
    source = next(e for e in ebon["entities"] if e["id"] == ebon["primaryEntityId"])
    event, = source["events"]
    assert (event["event"], event["actionCode"], event["count"], event["delayTicks"], event["damageBasis"], event["damageMultiplier"]) == (
        "on_hit", 1, 3, 0, "authored_child", 1)
    child = next(e for e in ebon["entities"] if e["id"] == event["entityId"])
    assert child["damage"]["damage"] == 3
    assert child["spawn"]["speedPxPerTick"] == 4
    assert child["movement"]["params"]["gravityPerTick"] == .18
    assert child["lifetimeTicks"] == 40

    assert rows == before
