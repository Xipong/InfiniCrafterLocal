"""Native sentry, explicit placement and descendant accounting remain independent."""
from copy import deepcopy

import pytest
from repair_test_helpers import frozen_call_repair

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def _fixture(sentry=None, pool=None, placement="item_use_origin"):
    doc = build_capability_witness("target_and_fire")
    root = next(c["target"] for c in doc["runtimeProgram"]["calls"] if c["fn"] == "target_and_fire")
    for call in doc["runtimeProgram"]["calls"]:
        if call["fn"] == "spawn" and call["target"] == root:
            call["params"]["position"] = {"at": "activation_origin" if placement == "item_use_origin" else placement}
    for ident, fn, params in (("native", "sentry", {"enabled": sentry}),
                              ("pool", "descendant_limit", {"maxActive": pool})):
        if next(iter(params.values())) is not None:
            doc["runtimeProgram"]["calls"].append({"id": ident, "fn": fn, "target": root, "params": params})
    return doc


def _entity(wire):
    return next(e for e in wire["runtimeProgram"]["entities"] if e.get("targeting"))


# Every pair of placement, native registration and pool presence is covered.
# The all-on native resting witness and numeric endpoints are explicit.
@pytest.mark.parametrize("native,pool,placement", [
    (None, None, "item_use_origin"), (False, 3, "item_use_origin"), (True, None, "item_use_origin"),
    (None, 3, "cursor"), (False, None, "cursor"), (True, 3, "cursor"),
    (None, None, "native_resting_spot"), (False, 3, "native_resting_spot"),
    (True, 3, "native_resting_spot"),
    pytest.param(True, 1, "native_resting_spot", id="native-pool-minimum"),
    pytest.param(True, 96, "native_resting_spot", id="native-pool-maximum"),
])
def test_pairwise_sentry_choices_preserve_exact_authored_delta(native, pool, placement):
    base = compile_runtime_program(_fixture())
    doc = _fixture(native, pool, placement)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    expected = deepcopy(base["runtimeProgram"])
    root = _entity({"runtimeProgram": expected})
    root["spawn"]["placement"] = placement
    if native is not None:
        root["nativeSentry"] = native
    if pool is not None:
        root["spawn"]["descendantMaxActive"] = pool
    assert wire["runtimeProgram"] == expected
    assert doc == before
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    for fn, value, suffix in (("sentry", native, ".nativeSentry"),
                               ("descendant_limit", pool, ".spawn.descendantMaxActive")):
        rows = [r for r in receipts if r.get("fn") == fn]
        assert len(rows) == (value is not None)
        if rows:
            assert rows[0]["value"] == value and rows[0]["status"] == "delivered"
            assert rows[0]["finalPath"].endswith(suffix)
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"]


@pytest.mark.parametrize("fn,key,bad", [
    *(('sentry', 'enabled', v) for v in (None, 1, "true", {})),
    *(('descendant_limit', 'maxActive', v) for v in (None, True, 0, 97, 1.0, "3", [])),
])
def test_present_invalid_values_are_red_without_coercion_or_provenance(fn, key, bad):
    doc = _fixture(True, 3)
    wire = compile_runtime_program(doc); wire.pop("runtimeContract")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"][key] = bad
    root = _entity(wire)
    path = ".nativeSentry" if fn == "sentry" else ".spawn.descendantMaxActive"
    target = root if fn == "sentry" else root["spawn"]
    target[path.rsplit('.', 1)[-1]] = bad
    for value, validator, suffix in ((doc, validate_runtime_program, ".params." + key), (wire, validate_runtime_wire, path)):
        before = deepcopy(value); report = validator(value)
        assert not report["ok"]
        assert any(r["path"].endswith(suffix) for r in report["errors"])
        assert value == before


@pytest.mark.parametrize("fn", ("sentry", "descendant_limit"))
def test_missing_required_choice_and_item_body_target_remain_red(fn):
    doc = build_capability_witness(fn)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"] = {}
    assert not validate_runtime_program(doc)["ok"]
    doc = build_capability_witness(fn)
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)["target"] = "item"
    assert not validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(_fixture())
    wire.pop("runtimeContract")
    item = wire["runtimeProgram"]["entities"][0]
    if fn == "sentry":
        item["nativeSentry"] = False
    else:
        item.setdefault("spawn", {})["descendantMaxActive"] = 1
    assert not validate_runtime_wire(wire)["ok"]


def test_frozen_repair_can_fix_pool_limit_without_enabling_native_or_changing_placement():
    good = _fixture(pool=3)
    broken = deepcopy(good)
    next(c for c in broken["runtimeProgram"]["calls"] if c["id"] == "pool")["params"]["maxActive"] = 0
    hostile = _fixture(True, 3, "native_resting_spot")
    repaired, final = frozen_call_repair(broken, hostile["runtimeProgram"]["calls"],
        [{"id": "pool", "paths": ["params.maxActive"]}], good, note="pool correction")
    assert _entity(final)["spawn"]["descendantMaxActive"] == 3
    assert "nativeSentry" not in _entity(final)


def test_accepted_absence_of_lifecycle_and_pool_is_not_materialized():
    doc = _fixture(); before = deepcopy(doc)
    wire = compile_runtime_program(doc); wire.pop("runtimeContract")
    assert all("nativeSentry" not in e and "descendantMaxActive" not in e.get("spawn", {}) for e in wire["runtimeProgram"]["entities"])
    before_wire = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"]
    assert wire == before_wire and doc == before
