"""Native sentry, explicit placement and descendant accounting remain independent."""
from copy import deepcopy
from itertools import product
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    compile_runtime_program, filter_repair_patch_scope,
    validate_runtime_program, validate_runtime_wire,
)
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.qa.capability_library_audit import _runtime_param_bound_rows
from infini_local.qa.capability_witnesses import build_capability_witness


def _fixture(sentry=None, pool=None, placement="item_use_origin"):
    doc = build_capability_witness("target_and_fire")
    root = next(c["target"] for c in doc["runtimeProgram"]["calls"] if c["fn"] == "target_and_fire")
    for call in doc["runtimeProgram"]["calls"]:
        if call["fn"] == "configure_spawn" and call["target"] == root:
            call["params"]["position"] = {"at": "activation_origin" if placement == "item_use_origin" else placement}
    for ident, fn, params in (("native", "set_projectile_sentry", {"enabled": sentry}),
                              ("pool", "set_descendant_concurrency", {"maxActive": pool})):
        if next(iter(params.values())) is not None:
            doc["runtimeProgram"]["calls"].append({"id": ident, "fn": fn, "target": root, "params": params})
    return doc


def _entity(wire):
    return next(e for e in wire["runtimeProgram"]["entities"] if e.get("targeting"))


@pytest.mark.parametrize("native,pool,placement", list(product(
    (None, False, True), (None, 1, 3, 96), ("item_use_origin", "cursor", "native_resting_spot"))))
def test_every_independent_combination_preserves_exact_authored_delta(native, pool, placement):
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
    for fn, value, suffix in (("set_projectile_sentry", native, ".nativeSentry"),
                               ("set_descendant_concurrency", pool, ".spawn.descendantMaxActive")):
        rows = [r for r in receipts if r.get("fn") == fn]
        assert len(rows) == (value is not None)
        if rows:
            assert rows[0]["value"] == value and rows[0]["status"] == "delivered"
            assert rows[0]["finalPath"].endswith(suffix)
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"]


@pytest.mark.parametrize("fn,key,bad", [
    *(('set_projectile_sentry', 'enabled', v) for v in (None, 0, 1, "true", {}, [])),
    *(('set_descendant_concurrency', 'maxActive', v) for v in (None, True, False, 0, 97, 1.0, "3", {}, [])),
])
def test_present_invalid_values_are_red_without_coercion_or_provenance(fn, key, bad):
    doc = _fixture(True, 3)
    wire = compile_runtime_program(doc); wire.pop("runtimeContract")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"][key] = bad
    root = _entity(wire)
    path = ".nativeSentry" if fn == "set_projectile_sentry" else ".spawn.descendantMaxActive"
    target = root if fn == "set_projectile_sentry" else root["spawn"]
    target[path.rsplit('.', 1)[-1]] = bad
    for value, validator, suffix in ((doc, validate_runtime_program, ".params." + key), (wire, validate_runtime_wire, path)):
        before = deepcopy(value); report = validator(value)
        assert not report["ok"]
        assert any(r["path"].endswith(suffix) for r in report["errors"])
        assert value == before


@pytest.mark.parametrize("fn", ("set_projectile_sentry", "set_descendant_concurrency"))
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
    if fn == "set_projectile_sentry":
        item["nativeSentry"] = False
    else:
        item.setdefault("spawn", {})["descendantMaxActive"] = 1
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("mode", ("json_object", "json_schema"))
def test_production_author_request_carries_independent_native_choices(monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    _, content, _ = build_initial_author_request({}, {}, {}, {}, "native-sentry", model_name="test-model")
    cards = {c["fn"]: c for c in json.loads(content)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    for fn in ("set_projectile_sentry", "set_descendant_concurrency"):
        assert cards[fn] == CAPABILITY_REGISTRY[fn].author_prompt_card()
        assert all(s.default is None for s in CAPABILITY_REGISTRY[fn].params.values())
    assert "FindSentryRestingSpot" in json.dumps(cards["configure_spawn"])
    assert "UpdateMaxTurrets" in cards["set_projectile_sentry"]["does"]
    assert "ancestor lifetime ledger" in cards["set_descendant_concurrency"]["does"]
    assert "network hydration" in cards["set_descendant_concurrency"]["does"]


def test_frozen_repair_can_fix_pool_limit_without_enabling_native_or_changing_placement():
    good = _fixture(pool=3)
    broken = deepcopy(good)
    next(c for c in broken["runtimeProgram"]["calls"] if c["id"] == "pool")["params"]["maxActive"] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": "pool", "paths": ["params.maxActive"]}]
    hostile = _fixture(True, 3, "native_resting_spot")
    patch = {"callsUpsert": hostile["runtimeProgram"]["calls"], "note": "pool correction"}
    filtered, audit = filter_repair_patch_scope(broken, patch, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    assert apply_repair_patch(broken, filtered) == good


def test_accepted_absence_of_lifecycle_and_pool_is_not_materialized():
    doc = _fixture(); before = deepcopy(doc)
    wire = compile_runtime_program(doc); wire.pop("runtimeContract")
    assert all("nativeSentry" not in e and "descendantMaxActive" not in e.get("spawn", {}) for e in wire["runtimeProgram"]["entities"])
    before_wire = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"]
    assert wire == before_wire and doc == before


def test_descendant_capacity_range_is_strictly_audited():
    rows = [r for r in _runtime_param_bound_rows() if r["capability"] == "set_descendant_concurrency"]
    assert len(rows) == 1 and rows[0]["preserved"]
    assert rows[0]["csharpBounds"] == [1, 96] and rows[0]["admission"] == "reject_without_clamp"


def test_mutated_descendant_range_is_red(monkeypatch):
    read = Path.read_text
    def mutant(path, *args, **kwargs):
        text = read(path, *args, **kwargs)
        if path.name == "RuntimeProgramSpec.cs":
            start = text.index("public int? DescendantMaxActive")
            text = text[:start] + text[start:].replace("value < 1", "value < 0", 1)
        return text
    monkeypatch.setattr(Path, "read_text", mutant)
    assert not next(r for r in _runtime_param_bound_rows() if r["capability"] == "set_descendant_concurrency")["preserved"]
