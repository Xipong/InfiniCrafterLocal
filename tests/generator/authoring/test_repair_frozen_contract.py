"""Frozen JSON/Repair semantics use current inputs; archives are refusal-only."""
from suite_paths import TEST_ROOT
import copy
import hashlib
import json
from pathlib import Path

import infini_local.pipelines.visual.contract as visual_contract
import infini_local.pipelines.visual.repair as visual_repair
import infini_local.pipelines.visual.repair_scope as visual_repair_scope
import pytest
from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from tests.generator.vfx.test_visual_presentation_metadata import kit


_FIXTURES = (TEST_ROOT / "fixtures")
_REPLAY_RAW = (_FIXTURES / "live20_repair_boundary_replay.json").read_bytes()
_REPLAY = json.loads(_REPLAY_RAW)


def test_current_initial_projectile_lifetime_compiles_without_repair(monkeypatch):
    from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
    from infini_local.pipelines.author import request as author
    from infini_local.pipelines.author import stage as combine
    from tests.generator.authoring.test_gameplay_repair_readonly_context import _offline_builder

    current = build_capability_witness("target_and_fire")
    next(row for row in current["runtimeProgram"]["calls"]
         if row["fn"] == "projectile_lifetime" and row["target"] == "witness_entity")["params"]["lifetimeSeconds"] = 600
    assert validate_runtime_program(current)["ok"]
    before = copy.deepcopy(current)
    requests = []

    def respond(request, **_kwargs):
        requests.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": json.dumps(current)}}]}

    def no_repair(*_args, **_kwargs):
        raise AssertionError("current valid Author must not invoke Repair")

    _offline_builder(monkeypatch, "json_object", respond)
    monkeypatch.setattr(combine, "repair_author_item_after_failure", no_repair)
    initial = author.try_llm_plan({}, {}, "current-projectile-lifetime")
    assert initial is not None
    wire = combine.compile_and_validate_authored_runtime(
        initial, {}, {}, "current-projectile-lifetime",
        run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs))
    assert len(requests) == 1
    assert wire["debug"]["llmStageAccounting"]["gameplayRepairCalls"] == 0
    assert current == before and initial["runtimeProgram"] == current["runtimeProgram"]
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                   authored_document=current, final_document=wire)["ok"]
    assert next(row for row in wire["runtimeProgram"]["entities"]
                if row["id"] == "witness_entity")["lifetimeTicks"] == 36000
    archived = (_FIXTURES / "projectile_lifetime_initial_author.json").read_bytes()
    assert hashlib.sha256(archived).hexdigest() == "d9a149814d5fa0894e1757fe384882bffbfa20813c700f540c2a0b4404c6b89c"
    assert not validate_runtime_program(json.loads(archived))["ok"]


@pytest.mark.parametrize("original,candidate,paths,expected", [
    pytest.param({"leaf": True, "sibling": "old"}, {"leaf": 1, "sibling": "hostile"}, ["leaf"], {"leaf": 1, "sibling": "old"}, id="authorized-type-change-frozen-sibling"),
    pytest.param({"leaf": 1}, {"leaf": 1.0}, [], {"leaf": 1}, id="frozen-integer-not-float"),
    pytest.param({"nested": [{"leaf": False}]}, {"nested": [{"leaf": 0}]}, [], {"nested": [{"leaf": False}]}, id="nested-boolean-not-integer"),
    pytest.param({"profile": [1, True, 0]}, {"profile": [1, 1, 0]}, ["profile[1]"], {"profile": [1, True, 0]}, id="array-not-thawed-by-descendant"),
    pytest.param({"a": [None, False, 1, 1.0], "b": {"c": 0}}, {"b": {"c": 0}, "a": [None, False, 1, 1.0]}, [], {"a": [None, False, 1, 1.0], "b": {"c": 0}}, id="object-order-is-not-a-change"),
])
def test_frozen_json_permissions_preserve_types_and_unchanged_source(original, candidate, paths, expected):
    before = json.dumps(original), json.dumps(candidate)
    merged, _ignored, _accepted = merge_frozen_subtree(
        original, candidate, mutable_paths=paths, audit_path="$", allow_additions=False)
    assert json.dumps(merged, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert (json.dumps(original), json.dumps(candidate)) == before


@pytest.mark.parametrize("domain", ["entity", "item_grip"])
def test_visual_literal_member_deletion_is_exact(domain):
    raw = kit()
    if domain == "entity":
        original = raw["entities"][0]
        candidate = copy.deepcopy(original)
        candidate["scale"] = 2.0
        key, relative, patch_edits = "scale.extra", '["scale.extra"]', {"entitiesUpsert": [candidate]}
        original[key] = "foreign"
    else:
        original = raw["item"]
        original["grip"] = {"normalizedX": 0.25, "normalizedY": 0.75}
        key, relative = "normalizedX.extra", 'grip["normalizedX.extra"]'
        original["grip"][key] = "foreign"
        patch_edits = {"itemPatch": {"grip": {"normalizedX": 0.9, "normalizedY": 0.1}}}
    before = copy.deepcopy(raw)
    _, errors = visual_contract._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert errors
    scope = visual_repair_scope._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert (scope["fieldPermissions"]["entities"] if domain == "entity" else scope["fieldPermissions"]["itemPaths"]) == ([{"entityId": "opaque_id", "paths": [relative]}] if domain == "entity" else [relative])
    patch = {
        "schema": visual_contract.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": None, "equipOverlayPatch": None,
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "note": "remove literal member", **patch_edits}
    repaired, audit = visual_repair._apply_visual_repair_patch(raw, patch, scope, ["opaque_id"], return_audit=True)
    expected = copy.deepcopy(raw)
    (expected["entities"][0] if domain == "entity" else expected["item"]["grip"]).pop(key)
    assert repaired == expected, "visual_literal_member_and_frozen_siblings"
    assert audit["ok"] and audit["ignoredChanges"]
    assert not visual_contract._validate_kit(repaired, ["opaque_id"], "opaque_id", equipment_overlay_required=True)[1]
    assert raw == before


def test_replay_frozen_provenance():
    assert _REPLAY["schema"] == "infini.live20-repair-boundary-replay.v1"
    assert _REPLAY["sourceHead"] == "e73db62bde4bfa0254d79444faa4374efe9d15b3"
    assert (_FIXTURES / "live20_repair_boundary_replay.json").read_bytes() == _REPLAY_RAW


@pytest.mark.parametrize("section,case", [
    pytest.param(section, case, id=case)
    for section in ("gameplayApplyCases", "gameplayDiagnosticCases") for case in _REPLAY[section]
])
def test_archived_gameplay_is_refused_without_adaptation(section, case):
    original = _REPLAY[section][case]["initialAuthor"]
    before = copy.deepcopy(original)
    report = validate_runtime_program(original)
    assert not report["ok"]
    assert ("$.runtimeProgram.schema", "shape_const") in {(e["path"], e["code"]) for e in report["errors"]}
    with pytest.raises(ValueError):
        compile_runtime_program(original)
    assert original == before


@pytest.mark.parametrize("fn,leaf,invalid,valid", [
    ("projectile_lifetime", "lifetimeSeconds", -1, 600),
    ("tool_stats", "axePower", -1, 100),
    ("projectile_collision", "pierce", -2, 2),
])
def test_current_gameplay_repair_changes_only_the_invalid_executable_leaf(fn, leaf, invalid, valid):
    initial = build_capability_witness(fn)
    assert validate_runtime_program(initial)["ok"]
    target = next(row for row in initial["runtimeProgram"]["calls"] if row["fn"] == fn)
    target["params"][leaf] = invalid
    before = copy.deepcopy(initial)
    report = validate_runtime_program(initial)
    assert not report["ok"]
    scope = build_runtime_repair_scope(initial, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": target["id"], "paths": ["params." + leaf]}]
    corrected = copy.deepcopy(target)
    corrected["params"][leaf] = valid
    hostile = copy.deepcopy(next(row for row in initial["runtimeProgram"]["calls"] if row["fn"] == "item_stats"))
    hostile["params"]["damage"] = 1999
    patch, audit = filter_repair_patch_scope(initial, {"callsUpsert": [corrected, hostile], "note": "exact leaf"}, scope)
    expected = copy.deepcopy(initial)
    next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == target["id"])["params"][leaf] = valid
    repaired = apply_repair_patch(initial, patch)
    assert audit["ok"] and audit["ignoredChanges"]
    assert repaired == expected and initial == before
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


def test_current_visual_literal_extra_deletion_keeps_the_valid_design():
    original = kit()
    assert not visual_contract._validate_kit(original, ["opaque_id"], "opaque_id", equipment_overlay_required=True)[1]
    original["item"][":palette"] = ["foreign"]
    before = copy.deepcopy(original)
    _, errors = visual_contract._validate_kit(original, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert [row["path"] for row in errors] == ['$.item[":palette"]']
    scope = visual_repair_scope._build_visual_repair_scope(original, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert scope["fieldPermissions"]["itemPaths"] == ['[":palette"]']
    patch = {"schema": visual_contract.VISUAL_REPAIR_PATCH_SCHEMA,
             "itemPatch": {"prompt": "hostile reauthoring"}, "equipOverlayPatch": None, "entitiesUpsert": [],
             "entityIdsDelete": [], "entityIndicesDelete": [], "note": "remove foreign literal member"}
    repaired, audit = visual_repair._apply_visual_repair_patch(original, patch, scope, ["opaque_id"], return_audit=True)
    expected = copy.deepcopy(original)
    del expected["item"][":palette"]
    assert audit["ok"] and audit["ignoredChanges"]
    assert repaired == expected and original == before
    assert not visual_contract._validate_kit(repaired, ["opaque_id"], "opaque_id", equipment_overlay_required=True)[1]
    archived = _REPLAY["visualApplyCases"]["woodwork_blade"]
    raw = copy.deepcopy(archived["visualRaw"])
    assert visual_contract._validate_kit(raw, archived["entityIds"], archived["itemBodyId"])[1]
    assert raw == archived["visualRaw"]
